"""MapBlock serialization for Luanti world format version 25.

Produces binary blobs matching MC2MT's MTBlock::serialize() output.
Reference: MC2MT/src/MTMap.cpp lines 297-415.
"""

import struct
import zlib

from earth2mt.config import MAP_BLOCK_SIZE, NODES_PER_BLOCK, SER_FMT_VER, AIR

# Light value: day light in lower nibble, max(block_light, sky_light) in upper nibble
# For our generated terrain: full sunlight above ground, dark underground
LIGHT_FULL = 0xFF  # sky=15, block=15
LIGHT_NONE = 0x00


def serialize_mapblock(block_data, mb_x: int, mb_y: int, mb_z: int) -> bytes:
    """Serialize a MapBlockData into the binary format for map.sqlite.

    Args:
        block_data: MapBlockData instance with .nodes list[str] of 4096 entries
        mb_x, mb_y, mb_z: MapBlock coordinates

    Returns:
        bytes ready to be stored in the database
    """
    buf = bytearray()

    # Version
    buf.append(SER_FMT_VER)  # 25

    # Flags
    flags = 0x08  # generated = true
    if mb_y < -1:
        flags |= 0x01  # is_underground
    flags |= 0x02  # day_night_differs
    buf.append(flags)

    # content_width = 2, params_width = 2
    buf.append(2)
    buf.append(2)

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

    # Serialize node data (ZYX order: z outer, y middle, x inner)
    node_buf = bytearray()

    # param0: content IDs (u16 big-endian)
    for z in range(MAP_BLOCK_SIZE):
        for y in range(MAP_BLOCK_SIZE):
            for x in range(MAP_BLOCK_SIZE):
                idx = z * MAP_BLOCK_SIZE * MAP_BLOCK_SIZE + y * MAP_BLOCK_SIZE + x
                local_id = name_to_local_id[block_data.nodes[idx]]
                node_buf.extend(struct.pack(">H", local_id))

    # param1: light values (u8)
    for z in range(MAP_BLOCK_SIZE):
        for y in range(MAP_BLOCK_SIZE):
            for x in range(MAP_BLOCK_SIZE):
                idx = z * MAP_BLOCK_SIZE * MAP_BLOCK_SIZE + y * MAP_BLOCK_SIZE + x
                node_name = block_data.nodes[idx]
                if node_name == AIR:
                    node_buf.append(LIGHT_FULL)
                elif node_name == "mcl_core:water_source":
                    # Water transmits some light
                    node_buf.append(0xEE)
                else:
                    node_buf.append(LIGHT_NONE)

    # param2: facedir etc. (u8, all 0 for terrain)
    node_buf.extend(b'\x00' * NODES_PER_BLOCK)

    # Compress and append node data
    buf.extend(zlib.compress(bytes(node_buf)))

    # Node metadata (empty)
    meta_buf = bytearray()
    meta_buf.append(0)  # version = 0 means empty
    buf.extend(zlib.compress(bytes(meta_buf)))

    # Static objects
    buf.append(0)  # version
    buf.extend(struct.pack(">H", 0))  # count = 0

    # Timestamp
    buf.extend(struct.pack(">I", 0xFFFFFFFF))  # undefined

    # Name-ID mapping
    buf.append(0)  # version
    buf.extend(struct.pack(">H", len(local_id_to_name)))
    for local_id, name in enumerate(local_id_to_name):
        name_bytes = name.encode("utf-8")
        buf.extend(struct.pack(">H", local_id))
        buf.extend(struct.pack(">H", len(name_bytes)))
        buf.extend(name_bytes)

    # Node timers
    buf.append(2 + 4 + 4)  # timer data length = 10
    buf.extend(struct.pack(">H", 0))  # count = 0

    return bytes(buf)
