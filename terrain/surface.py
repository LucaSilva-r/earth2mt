"""Surface generation pipeline - generates MapBlock column data from geographic data."""

import numpy as np

from earth2mt.config import (
    MAP_BLOCK_SIZE, NODES_PER_BLOCK,
    SEA_LEVEL, WORLD_FLOOR,
    STONE, WATER, AIR, SNOW_LAYER,
    GRASS_BLOCK, GRASS_BLOCK_SNOW, PODZOL, PODZOL_SNOW,
    Biome, Landform,
)
from earth2mt.terrain.coords import CoordinateTransform
from earth2mt.terrain.biome import classify_biome, determine_landform
from earth2mt.terrain.soil import (
    GrowthPredictors,
    compute_slope,
    sample_soil_profile,
    select_soil_texture,
)
from earth2mt.data.elevation import ElevationSource
from earth2mt.data.landcover import LandcoverSource
from earth2mt.data.climate import ClimateSource
from earth2mt.data.soil import OrganicCarbonSource, SoilClassSource

BIOME_BASE_TEMPERATURES = {
    Biome.DEEP_OCEAN: 0.5,
    Biome.OCEAN: 0.5,
    Biome.FROZEN_RIVER: 0.0,
    Biome.RIVER: 0.5,
    Biome.COLD_BEACH: 0.05,
    Biome.BEACH: 0.8,
    Biome.COLD_TAIGA: -0.5,
    Biome.ICE_PLAINS: 0.0,
    Biome.SWAMPLAND: 0.8,
    Biome.JUNGLE: 0.95,
    Biome.JUNGLE_EDGE: 0.95,
    Biome.DESERT: 2.0,
    Biome.TAIGA: 0.25,
    Biome.SAVANNA: 1.2,
    Biome.ROOFED_FOREST: 0.7,
    Biome.FOREST: 0.7,
    Biome.BIRCH_FOREST: 0.6,
    Biome.PLAINS: 0.8,
}

SNOW_TEMPERATURE_THRESHOLD = 0.15


def _surface_biome_temperature(biome: Biome, surface_y: int) -> float:
    temperature = BIOME_BASE_TEMPERATURES.get(biome, 0.8)
    if surface_y > 64:
        temperature -= ((surface_y - 64) * 0.05) / 30.0
    return temperature


def _supports_surface_snow(biome: Biome, terrain_h: int) -> bool:
    return _surface_biome_temperature(biome, terrain_h + 1) < SNOW_TEMPERATURE_THRESHOLD


def _snowify_surface_block(block: str) -> str:
    if block == GRASS_BLOCK:
        return GRASS_BLOCK_SNOW
    if block == PODZOL:
        return PODZOL_SNOW
    return block


def generate_mapblock_column(
    mb_x: int,
    mb_z: int,
    coords: CoordinateTransform,
    elevation_src: ElevationSource,
    landcover_src: LandcoverSource,
    climate_src: ClimateSource,
    organic_carbon_src: OrganicCarbonSource,
    soil_class_src: SoilClassSource,
    world_seed: int,
) -> list[tuple[int, "MapBlockData"]]:
    """Generate all MapBlocks for a single (mb_x, mb_z) column.

    Returns list of (mb_y, MapBlockData) tuples for non-empty blocks.
    """
    # First pass: sample data for all 16x16 columns in this MapBlock column
    base_bx = mb_x * MAP_BLOCK_SIZE
    base_bz = mb_z * MAP_BLOCK_SIZE

    # Per-column data arrays
    heights = np.zeros((MAP_BLOCK_SIZE, MAP_BLOCK_SIZE), dtype=np.int32)
    snow_cover = np.zeros((MAP_BLOCK_SIZE, MAP_BLOCK_SIZE), dtype=np.bool_)
    soil_profiles = [[[] for _ in range(MAP_BLOCK_SIZE)] for _ in range(MAP_BLOCK_SIZE)]

    elevations = elevation_src.sample_region(
        coords,
        base_bx - 1,
        base_bz - 1,
        MAP_BLOCK_SIZE + 2,
        MAP_BLOCK_SIZE + 2,
    )

    max_height = -9999

    for dz in range(MAP_BLOCK_SIZE):
        for dx in range(MAP_BLOCK_SIZE):
            bx = base_bx + dx
            bz = base_bz + dz

            # Sample geographic data
            lat, lon = coords.block_to_geo(bx, bz)
            elev = float(elevations[dz + 1, dx + 1])
            cover = landcover_src.sample(coords, bx, bz)
            mean_temp, min_temp, rainfall = climate_src.sample(lat, lon)
            organic_carbon = organic_carbon_src.sample(coords, bx, bz)
            soil_suborder = soil_class_src.sample(coords, bx, bz)
            slope = compute_slope(elevations, dx + 1, dz + 1, 1.0 / coords.scale)

            # Classify biome
            biome = classify_biome(elev, cover, mean_temp, min_temp, rainfall)
            landform = determine_landform(cover, elev)
            if biome in (Biome.BEACH, Biome.COLD_BEACH):
                landform = Landform.BEACH

            # Terrain height in blocks, with optional vertical exaggeration.
            terrain_h = coords.elevation_to_world_y(elev, SEA_LEVEL)
            heights[dz, dx] = terrain_h

            predictors = GrowthPredictors(
                annual_rainfall=rainfall,
                organic_carbon_content=organic_carbon,
                slope=slope,
                cover=cover,
                soil_suborder=soil_suborder,
                landform=landform,
            )
            texture = select_soil_texture(predictors)
            soil_profiles[dz][dx] = sample_soil_profile(
                texture,
                world_seed,
                bx,
                terrain_h,
                bz,
                slope,
            )
            snow_cover[dz, dx] = _supports_surface_snow(biome, terrain_h) and terrain_h >= SEA_LEVEL
            if snow_cover[dz, dx] and soil_profiles[dz][dx]:
                soil_profiles[dz][dx][0] = _snowify_surface_block(soil_profiles[dz][dx][0])

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
            mb_y, heights, snow_cover, soil_profiles, water_level
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
    heights: np.ndarray,
    snow_cover: np.ndarray,
    soil_profiles: list[list[list[str]]],
    water_level: int,
) -> MapBlockData | None:
    """Generate a single MapBlock at the given y-level."""
    block = MapBlockData()
    base_by = mb_y * MAP_BLOCK_SIZE
    has_content = False

    for dz in range(MAP_BLOCK_SIZE):
        for dx in range(MAP_BLOCK_SIZE):
            terrain_h = int(heights[dz, dx])
            soil_profile = soil_profiles[dz][dx]
            soil_depth = len(soil_profile)

            for dy in range(MAP_BLOCK_SIZE):
                world_y = base_by + dy

                if snow_cover[dz, dx] and world_y == terrain_h + 1:
                    block.set(dx, dy, dz, SNOW_LAYER)
                    has_content = True
                    continue
                if world_y > max(terrain_h, water_level):
                    # Above everything -> air
                    continue
                elif world_y > terrain_h and world_y <= water_level:
                    # Water
                    block.set(dx, dy, dz, WATER)
                    has_content = True
                else:
                    depth = terrain_h - world_y
                    if 0 <= depth < soil_depth:
                        block.set(dx, dy, dz, soil_profile[depth])
                    else:
                        # Deep underground -> stone
                        block.set(dx, dy, dz, STONE)
                    has_content = True

    if not has_content:
        return None

    return block
