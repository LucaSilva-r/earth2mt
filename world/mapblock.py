"""MapBlock serialization for Luanti world format version 25.

Produces binary blobs matching MC2MT's MTBlock::serialize() output.
Reference: MC2MT/src/MTMap.cpp lines 297-415.
"""

import struct
import zlib

from earth2mt.config import MAP_BLOCK_SIZE, NODES_PER_BLOCK, SER_FMT_VER, AIR, SNOW_LAYER
from earth2mt.vegetation.generator import is_light_transparent_vegetation

# Light value: day light in lower nibble, night light in upper nibble.
# We do not place artificial lights while generating terrain, so the night bank
# is always zero and only sky light needs to be tracked.
DAYLIGHT_FULL = 0x0F
LIGHT_NONE = 0x00

LIGHT_TRANSPARENT_NODES = frozenset({
    AIR,
    SNOW_LAYER,
    "mcl_core:water_source",
    "mcl_core:ice",
})


def _is_light_transparent(node_name: str) -> bool:
    return node_name in LIGHT_TRANSPARENT_NODES or is_light_transparent_vegetation(node_name)


def _node_index(x: int, y: int, z: int) -> int:
    return z * MAP_BLOCK_SIZE * MAP_BLOCK_SIZE + y * MAP_BLOCK_SIZE + x


def _serialize_single_mapblock(
    block_data,
    mb_y: int,
    local_id_by_name: dict[str, int],
    light_bytes: bytes,
) -> bytes:
    """Serialize one MapBlockData with precomputed local IDs and light bytes."""
    node_buf = bytearray()

    # param0: content IDs (u16 big-endian)
    for z in range(MAP_BLOCK_SIZE):
        for y in range(MAP_BLOCK_SIZE):
            for x in range(MAP_BLOCK_SIZE):
                idx = _node_index(x, y, z)
                local_id = local_id_by_name[block_data.nodes[idx]]
                node_buf.extend(struct.pack(">H", local_id))

    # param1: light values (u8)
    node_buf.extend(light_bytes)

    # param2: facedir, palettes, and other per-node parameters.
    node_buf.extend(bytes(getattr(block_data, "param2", [0] * NODES_PER_BLOCK)))

    buf = bytearray()
    buf.append(SER_FMT_VER)  # 25

    flags = 0x08  # generated = true
    if mb_y < -1:
        flags |= 0x01  # is_underground
    flags |= 0x02  # day_night_differs
    buf.append(flags)

    buf.append(2)  # content_width
    buf.append(2)  # params_width
    buf.extend(zlib.compress(bytes(node_buf)))
    return bytes(buf)


def _write_string(buf: bytearray, value: str):
    data = value.encode("utf-8")
    buf.extend(struct.pack(">H", len(data)))
    buf.extend(data)


def _write_long_string(buf: bytearray, value: bytes | str):
    data = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    buf.extend(struct.pack(">I", len(data)))
    buf.extend(data)


def _serialize_node_metadata(block_data) -> bytes:
    node_metadata = getattr(block_data, "node_metadata", {})
    meta_buf = bytearray()
    if not node_metadata:
        meta_buf.append(0)
        return zlib.compress(bytes(meta_buf))

    meta_buf.append(1)
    meta_buf.extend(struct.pack(">H", len(node_metadata)))
    for idx in sorted(node_metadata):
        metadata = node_metadata[idx]
        meta_buf.extend(struct.pack(">H", idx))
        meta_buf.extend(struct.pack(">I", len(metadata)))
        for key in sorted(metadata):
            _write_string(meta_buf, key)
            _write_long_string(meta_buf, metadata[key])
        meta_buf.extend(b"EndInventory\n")
    return zlib.compress(bytes(meta_buf))


def _append_common_trailers(block_bytes: bytearray, local_id_to_name: list[str], block_data):
    block_bytes.extend(_serialize_node_metadata(block_data))

    # Static objects
    block_bytes.append(0)
    block_bytes.extend(struct.pack(">H", 0))

    # Timestamp
    block_bytes.extend(struct.pack(">I", 0xFFFFFFFF))

    # Name-ID mapping
    block_bytes.append(0)
    block_bytes.extend(struct.pack(">H", len(local_id_to_name)))
    for local_id, name in enumerate(local_id_to_name):
        name_bytes = name.encode("utf-8")
        block_bytes.extend(struct.pack(">H", local_id))
        block_bytes.extend(struct.pack(">H", len(name_bytes)))
        block_bytes.extend(name_bytes)

    # Node timers
    block_bytes.append(2 + 4 + 4)
    block_bytes.extend(struct.pack(">H", 0))


def _compute_column_light_bytes(
    mapblocks: list[tuple[int, "MapBlockData"]],
) -> dict[int, bytes]:
    """Compute sky light for all mapblocks in one X/Z column.

    The generator produces a heightfield, so sunlight only needs to travel
    vertically downwards until the first opaque node in each local X/Z column.
    """
    blocks_by_y = {mb_y: block_data for mb_y, block_data in mapblocks}
    sorted_mb_y = sorted(blocks_by_y, reverse=True)
    light_buffers = {mb_y: bytearray(NODES_PER_BLOCK) for mb_y in blocks_by_y}

    for z in range(MAP_BLOCK_SIZE):
        for x in range(MAP_BLOCK_SIZE):
            has_sunlight = True
            for mb_y in sorted_mb_y:
                block_data = blocks_by_y[mb_y]
                light_buffer = light_buffers[mb_y]

                for y in range(MAP_BLOCK_SIZE - 1, -1, -1):
                    idx = _node_index(x, y, z)
                    node_name = block_data.nodes[idx]
                    is_transparent = _is_light_transparent(node_name)

                    light_buffer[idx] = DAYLIGHT_FULL if has_sunlight and is_transparent else LIGHT_NONE

                    if not is_transparent:
                        has_sunlight = False

    return {mb_y: bytes(light_buffers[mb_y]) for mb_y in light_buffers}


def serialize_mapblock(block_data, mb_x: int, mb_y: int, mb_z: int) -> bytes:
    """Serialize a MapBlockData into the binary format for map.sqlite.

    Args:
        block_data: MapBlockData instance with .nodes list[str] of 4096 entries
        mb_x, mb_y, mb_z: MapBlock coordinates

    Returns:
        bytes ready to be stored in the database
    """
    # Build per-block name-ID mapping
    name_to_local_id: dict[str, int] = {}
    local_id_to_name: list[str] = []
    next_id = 0

    # Pre-scan to build mapping
    for node_name in block_data.nodes:
        if node_name not in name_to_local_id:
            name_to_local_id[node_name] = next_id
            local_id_to_name.append(node_name)
            next_id += 1

    light_bytes = bytes(NODES_PER_BLOCK)
    buf = bytearray(_serialize_single_mapblock(block_data, mb_y, name_to_local_id, light_bytes))

    _append_common_trailers(buf, local_id_to_name, block_data)
    return bytes(buf)


def serialize_mapblock_column(
    mapblocks: list[tuple[int, "MapBlockData"]],
    mb_x: int,
    mb_z: int,
) -> list[tuple[int, bytes]]:
    """Serialize all blocks in one X/Z mapblock column with consistent lighting."""
    if not mapblocks:
        return []

    light_by_mb_y = _compute_column_light_bytes(mapblocks)
    serialized = []
    for mb_y, block_data in mapblocks:
        # Build a local name-ID mapping per serialized block, like Luanti expects.
        name_to_local_id: dict[str, int] = {}
        next_id = 0
        for node_name in block_data.nodes:
            if node_name not in name_to_local_id:
                name_to_local_id[node_name] = next_id
                next_id += 1

        block_bytes = bytearray(
            _serialize_single_mapblock(block_data, mb_y, name_to_local_id, light_by_mb_y[mb_y])
        )

        local_id_to_name = [None] * len(name_to_local_id)
        for name, local_id in name_to_local_id.items():
            local_id_to_name[local_id] = name

        _append_common_trailers(block_bytes, local_id_to_name, block_data)
        serialized.append((mb_y, bytes(block_bytes)))

    return serialized
