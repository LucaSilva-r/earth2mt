"""Parser for Terrarium's custom raster binary format.

Format (version 0):
  - 16 bytes: signature "TERRARIUM/RASTER"
  - 1 byte: version (0)
  - 4 bytes: width (big-endian int32)
  - 4 bytes: height (big-endian int32)
  - 1 byte: data_type (0=ubyte, 1=byte, 2=short)
  - Chunks until EOF:
    - 4 bytes: chunk_length (big-endian int32)
    - chunk_length bytes: chunk_data
      - 4 bytes: chunk_x
      - 4 bytes: chunk_y
      - 4 bytes: chunk_width
      - 4 bytes: chunk_height
      - 1 byte: filter_id (0=none, 1=left, 2=up, 3=average, 4=paeth)
      - remaining: XZ-compressed raster data
"""

import io
import lzma
import struct
import numpy as np

SIGNATURE = b"TERRARIUM/RASTER"


def read_raster(data: bytes) -> np.ndarray:
    """Parse a Terrarium raster file into a numpy array."""
    buf = io.BytesIO(data)

    sig = buf.read(16)
    if sig != SIGNATURE:
        raise ValueError(f"Invalid signature: {sig!r}")

    version = struct.unpack(">B", buf.read(1))[0]
    if version != 0:
        raise ValueError(f"Unknown raster version: {version}")

    width, height = struct.unpack(">ii", buf.read(8))
    data_type = struct.unpack(">B", buf.read(1))[0]

    if data_type == 0:
        dtype = np.uint8
        elem_size = 1
    elif data_type == 1:
        dtype = np.int8
        elem_size = 1
    elif data_type == 2:
        dtype = np.int16
        elem_size = 2
    else:
        raise ValueError(f"Unknown data type: {data_type}")

    result = np.zeros((height, width), dtype=dtype)

    while True:
        chunk_len_bytes = buf.read(4)
        if len(chunk_len_bytes) < 4:
            break

        chunk_len = struct.unpack(">i", chunk_len_bytes)[0]
        chunk_data = buf.read(chunk_len)
        if len(chunk_data) < chunk_len:
            break

        _parse_chunk(chunk_data, result, dtype, elem_size)

    return result


def _parse_chunk(chunk_data: bytes, result: np.ndarray, dtype, elem_size: int):
    """Parse a single chunk and write into the result array."""
    buf = io.BytesIO(chunk_data)

    chunk_x, chunk_y, chunk_w, chunk_h = struct.unpack(">iiii", buf.read(16))
    filter_id = struct.unpack(">B", buf.read(1))[0]

    # Decompress XZ data
    compressed = buf.read()
    raw_data = lzma.decompress(compressed, format=lzma.FORMAT_XZ)

    # Parse raw pixel data
    expected_size = chunk_w * chunk_h * elem_size
    if len(raw_data) < expected_size:
        raise ValueError(f"Chunk data too short: {len(raw_data)} < {expected_size}")

    if elem_size == 1:
        raw = np.frombuffer(raw_data[:expected_size], dtype=dtype).reshape((chunk_h, chunk_w))
    else:
        # Big-endian shorts
        raw = np.frombuffer(raw_data[:expected_size], dtype=">i2").reshape((chunk_h, chunk_w))

    # Apply PNG-style prediction filter
    filtered = _apply_filter(raw, filter_id)

    # Copy into result (clamped to bounds)
    dst_y_start = max(0, chunk_y)
    dst_y_end = min(result.shape[0], chunk_y + chunk_h)
    dst_x_start = max(0, chunk_x)
    dst_x_end = min(result.shape[1], chunk_x + chunk_w)

    src_y_start = dst_y_start - chunk_y
    src_y_end = src_y_start + (dst_y_end - dst_y_start)
    src_x_start = dst_x_start - chunk_x
    src_x_end = src_x_start + (dst_x_end - dst_x_start)

    result[dst_y_start:dst_y_end, dst_x_start:dst_x_end] = \
        filtered[src_y_start:src_y_end, src_x_start:src_x_end].astype(result.dtype)


def _apply_filter(raw: np.ndarray, filter_id: int) -> np.ndarray:
    """Apply PNG-style prediction filter to reconstruct original values.

    Filters: 0=none, 1=left, 2=up, 3=average, 4=paeth
    """
    if filter_id == 0:
        return raw

    h, w = raw.shape
    out = np.zeros_like(raw, dtype=np.int32)

    for y in range(h):
        for x in range(w):
            val = int(raw[y, x])
            a = int(out[y, x - 1]) if x > 0 else 0
            b = int(out[y - 1, x]) if y > 0 else 0
            c = int(out[y - 1, x - 1]) if (x > 0 and y > 0) else 0

            if filter_id == 1:  # LEFT
                out[y, x] = val + a
            elif filter_id == 2:  # UP
                out[y, x] = val + b
            elif filter_id == 3:  # AVERAGE
                out[y, x] = val + (a + b) // 2
            elif filter_id == 4:  # PAETH
                p = a + b - c
                da, db, dc = abs(a - p), abs(b - p), abs(c - p)
                if da < db and da < dc:
                    out[y, x] = val + a
                elif db < dc:
                    out[y, x] = val + b
                else:
                    out[y, x] = val + c

    return out
