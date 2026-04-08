"""Surface generation pipeline - generates MapBlock column data from geographic data."""

import numpy as np

from earth2mt.config import (
    MAP_BLOCK_SIZE, NODES_PER_BLOCK,
    SEA_LEVEL, WORLD_FLOOR,
    STONE, WATER, AIR, SNOW_LAYER,
    GRASS_BLOCK, GRASS_BLOCK_SNOW, PODZOL, PODZOL_SNOW,
    Biome, Cover, Landform,
)
from earth2mt.terrain.coords import CoordinateTransform
from earth2mt.terrain.biome import classify_biome, determine_landform
from earth2mt.terrain.mineclonia_biome import (
    MINECLONIA_BIOME_METADATA_KEY,
    PALETTE_NODES,
    classify_mineclonia_biome,
    encode_mapblock_biome_index,
    get_grass_palette_index,
    get_leaves_palette_index,
    get_mineclonia_biome_id,
)
from earth2mt.terrain.soil import (
    GrowthPredictors,
    compute_slope,
    sample_soil_profile,
    select_soil_texture,
)
from earth2mt.vegetation.generator import generate_vegetation_column
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


def _apply_landform_to_height(terrain_h: int, landform: Landform, sea_level: int) -> int:
    """Match Terrarium's water height adjustment around sea level."""
    if landform == Landform.SEA:
        return min(terrain_h, sea_level - 1)
    if landform == Landform.LAND and terrain_h < sea_level:
        return sea_level
    if landform == Landform.LAKE_OR_RIVER:
        return terrain_h - 1
    return terrain_h


def _normalize_cover_for_landform(cover: Cover, landform: Landform) -> Cover:
    """Mirror Terrarium's cover correction after landform generation."""
    if landform in (Landform.SEA, Landform.LAKE_OR_RIVER):
        return Cover.WATER
    if cover == Cover.WATER:
        return Cover.NO
    return cover


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
    biome_names = [["Plains" for _ in range(MAP_BLOCK_SIZE)] for _ in range(MAP_BLOCK_SIZE)]
    palette_indices = np.zeros((MAP_BLOCK_SIZE, MAP_BLOCK_SIZE), dtype=np.uint8)
    leaves_palette_indices = np.zeros((MAP_BLOCK_SIZE, MAP_BLOCK_SIZE), dtype=np.uint8)
    biome_ids = np.zeros((MAP_BLOCK_SIZE, MAP_BLOCK_SIZE), dtype=np.uint8)

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

            landform = determine_landform(cover, elev)
            terrain_h = coords.elevation_to_world_y(elev, SEA_LEVEL)
            terrain_h = _apply_landform_to_height(terrain_h, landform, SEA_LEVEL)
            cover = _normalize_cover_for_landform(cover, landform)

            # Classify biome
            biome = classify_biome(elev, cover, mean_temp, min_temp, rainfall)
            if biome in (Biome.BEACH, Biome.COLD_BEACH):
                landform = Landform.BEACH

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

            surface_block = soil_profiles[dz][dx][0] if soil_profiles[dz][dx] else None
            mineclonia_biome = classify_mineclonia_biome(
                biome,
                cover,
                mean_temp,
                min_temp,
                texture,
                bool(snow_cover[dz, dx]),
                surface_block,
            )
            palette_indices[dz, dx] = get_grass_palette_index(mineclonia_biome)
            leaves_palette_indices[dz, dx] = get_leaves_palette_index(mineclonia_biome)
            biome_ids[dz, dx] = get_mineclonia_biome_id(mineclonia_biome)
            biome_names[dz][dx] = mineclonia_biome

            max_height = max(max_height, terrain_h)

    vegetation_nodes, vegetation_max_y = generate_vegetation_column(
        base_bx,
        base_bz,
        heights,
        snow_cover,
        soil_profiles,
        biome_names,
        palette_indices,
        leaves_palette_indices,
        water_level=SEA_LEVEL,
        world_seed=world_seed,
    )

    # Determine y-range of MapBlocks we need to generate
    # We need blocks from WORLD_FLOOR up to max(max_height, SEA_LEVEL) + some margin
    water_level = SEA_LEVEL
    top_y = max(max_height, water_level) + 1  # +1 for the surface block
    if vegetation_nodes:
        top_y = max(top_y, vegetation_max_y)
    bottom_y = WORLD_FLOOR

    mb_y_min = bottom_y // MAP_BLOCK_SIZE
    mb_y_max = top_y // MAP_BLOCK_SIZE

    results = []
    biome_index = encode_mapblock_biome_index(biome_ids)

    for mb_y in range(mb_y_min, mb_y_max + 1):
        block_data = _generate_mapblock(
            mb_y,
            heights,
            snow_cover,
            soil_profiles,
            palette_indices,
            water_level,
            biome_index,
            vegetation_nodes,
        )
        if block_data is not None:
            results.append((mb_y, block_data))

    return results


class MapBlockData:
    """Holds the node data for a single 16x16x16 MapBlock."""
    __slots__ = ("nodes", "param2", "node_metadata")

    def __init__(self):
        # nodes[z * 256 + y * 16 + x] = block_name string
        self.nodes: list[str] = [AIR] * NODES_PER_BLOCK
        self.param2: list[int] = [0] * NODES_PER_BLOCK
        self.node_metadata: dict[int, dict[str, bytes | str]] = {}

    def set(self, x: int, y: int, z: int, block: str):
        self.nodes[z * MAP_BLOCK_SIZE * MAP_BLOCK_SIZE + y * MAP_BLOCK_SIZE + x] = block

    def set_param2(self, x: int, y: int, z: int, value: int):
        self.param2[z * MAP_BLOCK_SIZE * MAP_BLOCK_SIZE + y * MAP_BLOCK_SIZE + x] = value

    def set_metadata(self, x: int, y: int, z: int, key: str, value: bytes | str):
        idx = z * MAP_BLOCK_SIZE * MAP_BLOCK_SIZE + y * MAP_BLOCK_SIZE + x
        if idx not in self.node_metadata:
            self.node_metadata[idx] = {}
        self.node_metadata[idx][key] = value

    def get(self, x: int, y: int, z: int) -> str:
        return self.nodes[z * MAP_BLOCK_SIZE * MAP_BLOCK_SIZE + y * MAP_BLOCK_SIZE + x]

    def is_all_air(self) -> bool:
        return all(n == AIR for n in self.nodes)


def _generate_mapblock(
    mb_y: int,
    heights: np.ndarray,
    snow_cover: np.ndarray,
    soil_profiles: list[list[list[str]]],
    palette_indices: np.ndarray,
    water_level: int,
    biome_index: bytes,
    vegetation_nodes: dict[tuple[int, int, int], tuple[str, int]],
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
                decoration = vegetation_nodes.get((dx, world_y, dz))
                if decoration is not None:
                    node_name, param2 = decoration
                    block.set(dx, dy, dz, node_name)
                    if param2:
                        block.set_param2(dx, dy, dz, int(param2))
                    has_content = True
                    continue

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
                    node_name = block.get(dx, dy, dz)
                    if node_name in PALETTE_NODES:
                        block.set_param2(dx, dy, dz, int(palette_indices[dz, dx]))
                    has_content = True

    if not has_content:
        return None

    block.set_metadata(0, 0, 0, MINECLONIA_BIOME_METADATA_KEY, biome_index)
    return block
