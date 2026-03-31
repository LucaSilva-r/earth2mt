"""Surface generation pipeline - generates MapBlock column data from geographic data."""

import numpy as np

from earth2mt.config import (
    MAP_BLOCK_SIZE, NODES_PER_BLOCK,
    SEA_LEVEL, WORLD_FLOOR,
    STONE, WATER, AIR, IGNORE,
    Biome,
)
from earth2mt.terrain.coords import CoordinateTransform
from earth2mt.terrain.biome import classify_biome
from earth2mt.terrain.soil import select_surface_blocks, soil_depth
from earth2mt.data.elevation import ElevationSource
from earth2mt.data.landcover import LandcoverSource
from earth2mt.data.climate import ClimateSource


def generate_mapblock_column(
    mb_x: int,
    mb_z: int,
    coords: CoordinateTransform,
    elevation_src: ElevationSource,
    landcover_src: LandcoverSource,
    climate_src: ClimateSource,
) -> list[tuple[int, "MapBlockData"]]:
    """Generate all MapBlocks for a single (mb_x, mb_z) column.

    Returns list of (mb_y, MapBlockData) tuples for non-empty blocks.
    """
    # First pass: sample data for all 16x16 columns in this MapBlock column
    base_bx = mb_x * MAP_BLOCK_SIZE
    base_bz = mb_z * MAP_BLOCK_SIZE

    # Per-column data arrays
    heights = np.zeros((MAP_BLOCK_SIZE, MAP_BLOCK_SIZE), dtype=np.int32)
    biomes = np.zeros((MAP_BLOCK_SIZE, MAP_BLOCK_SIZE), dtype=np.int32)
    top_blocks = [[None] * MAP_BLOCK_SIZE for _ in range(MAP_BLOCK_SIZE)]
    sub_blocks = [[None] * MAP_BLOCK_SIZE for _ in range(MAP_BLOCK_SIZE)]
    depths = np.zeros((MAP_BLOCK_SIZE, MAP_BLOCK_SIZE), dtype=np.int32)

    min_height = 9999
    max_height = -9999

    for dz in range(MAP_BLOCK_SIZE):
        for dx in range(MAP_BLOCK_SIZE):
            bx = base_bx + dx
            bz = base_bz + dz

            # Sample geographic data
            lat, lon = coords.block_to_geo(bx, bz)
            elev = elevation_src.sample(coords, bx, bz)
            cover = landcover_src.sample(coords, bx, bz)
            mean_temp, min_temp, rainfall = climate_src.sample(lat, lon)

            # Classify biome
            biome = classify_biome(elev, cover, mean_temp, min_temp, rainfall)

            # Terrain height in blocks (elevation relative to sea level)
            terrain_h = int(round(elev)) + SEA_LEVEL
            heights[dz, dx] = terrain_h
            biomes[dz, dx] = biome

            # Surface blocks
            top, sub = select_surface_blocks(biome, bx, bz)
            top_blocks[dz][dx] = top
            sub_blocks[dz][dx] = sub
            depths[dz, dx] = soil_depth(bx, bz)

            min_height = min(min_height, terrain_h)
            max_height = max(max_height, terrain_h)

    # Determine y-range of MapBlocks we need to generate
    # We need blocks from WORLD_FLOOR up to max(max_height, SEA_LEVEL) + some margin
    water_level = SEA_LEVEL
    top_y = max(max_height, water_level) + 1  # +1 for the surface block
    bottom_y = WORLD_FLOOR

    mb_y_min = bottom_y // MAP_BLOCK_SIZE
    mb_y_max = top_y // MAP_BLOCK_SIZE

    results = []

    for mb_y in range(mb_y_min, mb_y_max + 1):
        block_data = _generate_mapblock(
            mb_y, base_bx, base_bz,
            heights, biomes, top_blocks, sub_blocks, depths,
            water_level,
        )
        if block_data is not None:
            results.append((mb_y, block_data))

    return results


class MapBlockData:
    """Holds the node data for a single 16x16x16 MapBlock."""
    __slots__ = ("nodes",)

    def __init__(self):
        # nodes[z * 256 + y * 16 + x] = block_name string
        self.nodes: list[str] = [AIR] * NODES_PER_BLOCK

    def set(self, x: int, y: int, z: int, block: str):
        self.nodes[z * MAP_BLOCK_SIZE * MAP_BLOCK_SIZE + y * MAP_BLOCK_SIZE + x] = block

    def get(self, x: int, y: int, z: int) -> str:
        return self.nodes[z * MAP_BLOCK_SIZE * MAP_BLOCK_SIZE + y * MAP_BLOCK_SIZE + x]

    def is_all_air(self) -> bool:
        return all(n == AIR for n in self.nodes)


def _generate_mapblock(
    mb_y: int,
    base_bx: int,
    base_bz: int,
    heights: np.ndarray,
    biomes: np.ndarray,
    top_blocks: list[list[str]],
    sub_blocks: list[list[str]],
    depths: np.ndarray,
    water_level: int,
) -> MapBlockData | None:
    """Generate a single MapBlock at the given y-level."""
    block = MapBlockData()
    base_by = mb_y * MAP_BLOCK_SIZE
    has_content = False

    for dz in range(MAP_BLOCK_SIZE):
        for dx in range(MAP_BLOCK_SIZE):
            terrain_h = int(heights[dz, dx])
            sdepth = int(depths[dz, dx])
            top = top_blocks[dz][dx]
            sub = sub_blocks[dz][dx]

            for dy in range(MAP_BLOCK_SIZE):
                world_y = base_by + dy

                if world_y > max(terrain_h, water_level):
                    # Above everything -> air
                    continue
                elif world_y > terrain_h and world_y <= water_level:
                    # Water
                    block.set(dx, dy, dz, WATER)
                    has_content = True
                elif world_y == terrain_h:
                    # Surface block
                    block.set(dx, dy, dz, top)
                    has_content = True
                elif world_y > terrain_h - sdepth:
                    # Subsurface soil
                    block.set(dx, dy, dz, sub)
                    has_content = True
                else:
                    # Deep underground -> stone
                    block.set(dx, dy, dz, STONE)
                    has_content = True

    if not has_content:
        return None

    return block
