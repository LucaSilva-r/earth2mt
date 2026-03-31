"""Constants: Mineclonia block names, climate thresholds, tile server config."""

from enum import IntEnum

# === Mineclonia Block Names ===

STONE = "mcl_core:stone"
DIRT = "mcl_core:dirt"
GRASS_BLOCK = "mcl_core:dirt_with_grass"
PODZOL = "mcl_core:podzol"
COARSE_DIRT = "mcl_core:coarse_dirt"
SAND = "mcl_core:sand"
RED_SAND = "mcl_core:redsand"
SANDSTONE = "mcl_core:sandstone"
RED_SANDSTONE = "mcl_core:redsandstone"
GRAVEL = "mcl_core:gravel"
CLAY = "mcl_core:clay"
WATER = "mcl_core:water_source"
SNOW_BLOCK = "mcl_core:snowblock"
BEDROCK = "mcl_core:bedrock"
ICE = "mcl_core:ice"
AIR = "air"
IGNORE = "ignore"

# === Geographic Constants ===

EQUATOR_CIRCUMFERENCE = 40_075_017  # meters

# === Tile Server ===

TILE_BASE_URL = "https://terrarium.gegy.dev/geo3"
TILE_SIZE = 1000  # pixels per tile
ZOOM_BASE = 3

# === Climate Thresholds (from Terrarium Climate.java) ===

MIN_FREEZE_TEMP = -14.0   # min_temp threshold for frozen
MEAN_COLD_TEMP = 5.0      # mean_temp threshold for cold/frozen
MEAN_WARM_TEMP = 18.0
MEAN_HOT_TEMP = 22.0
DESERT_RAINFALL = 250.0   # mm, below = desert
VERY_DRY_RAINFALL = 380.0 # mm, below = very dry
DRY_RAINFALL = 508.0      # mm, below = dry
RAINFOREST_RAINFALL = 1800.0
TAIGA_MIN_TEMP = -30.0
TAIGA_MAX_TEMP = 10.0
TROPICAL_RF_MIN_TEMP = 20.0

# === Surface Generation ===

SEA_LEVEL = 0  # y=0 is sea level in our world
MAX_SOIL_DEPTH = 6
WORLD_FLOOR = -64  # lowest y we generate stone down to

# === MapBlock ===

MAP_BLOCK_SIZE = 16
NODES_PER_BLOCK = MAP_BLOCK_SIZE ** 3
SER_FMT_VER = 25

# Content IDs for special nodes
CONTENT_IGNORE = 0
CONTENT_AIR = 1
CONTENT_FIRST = 2


class Biome(IntEnum):
    VOID = 0
    DEEP_OCEAN = 1
    OCEAN = 2
    FROZEN_RIVER = 3
    RIVER = 4
    COLD_BEACH = 5
    BEACH = 6
    COLD_TAIGA = 7
    ICE_PLAINS = 8
    SWAMPLAND = 9
    JUNGLE = 10
    JUNGLE_EDGE = 11
    DESERT = 12
    TAIGA = 13
    SAVANNA = 14
    ROOFED_FOREST = 15
    FOREST = 16
    BIRCH_FOREST = 17
    PLAINS = 18


class Landform(IntEnum):
    LAND = 0
    BEACH = 1
    SEA = 2
    LAKE_OR_RIVER = 3


class Cover(IntEnum):
    """Land cover types from ESA CCI, matching Terrarium's Cover.java enum IDs."""
    NO = 0
    RAINFED_CROPLAND = 10
    HERBACEOUS_COVER = 11
    TREE_OR_SHRUB_COVER = 12
    IRRIGATED_CROPLAND = 20
    CROPLAND_WITH_VEGETATION = 30
    VEGETATION_WITH_CROPLAND = 40
    BROADLEAF_EVERGREEN = 50
    BROADLEAF_DECIDUOUS = 60
    BROADLEAF_DECIDUOUS_CLOSED = 61
    BROADLEAF_DECIDUOUS_OPEN = 62
    NEEDLEAF_EVERGREEN = 70
    NEEDLEAF_EVERGREEN_CLOSED = 71
    NEEDLEAF_EVERGREEN_OPEN = 72
    NEEDLEAF_DECIDUOUS = 80
    NEEDLEAF_DECIDUOUS_CLOSED = 81
    NEEDLEAF_DECIDUOUS_OPEN = 82
    MIXED_LEAF_TYPE = 90
    TREE_AND_SHRUB_WITH_HERBACEOUS_COVER = 100
    HERBACEOUS_COVER_WITH_TREE_AND_SHRUB = 110
    SHRUBLAND = 120
    SHRUBLAND_EVERGREEN = 121
    SHRUBLAND_DECIDUOUS = 122
    GRASSLAND = 130
    LICHENS_AND_MOSSES = 140
    SPARSE_VEGETATION = 150
    SPARSE_TREE = 151
    SPARSE_SHRUB = 152
    SPARSE_HERBACEOUS_COVER = 153
    FRESH_FLOODED_FOREST = 160
    SALINE_FLOODED_FOREST = 170
    FLOODED_VEGETATION = 180
    URBAN = 190
    BARE = 200
    BARE_CONSOLIDATED = 201
    BARE_UNCONSOLIDATED = 202
    WATER = 210
    PERMANENT_SNOW = 220


# Lookup table: cover ID (0-255) -> Cover enum
_COVER_BY_ID = {c.value: c for c in Cover}


def cover_by_id(cid: int) -> Cover:
    return _COVER_BY_ID.get(cid, Cover.NO)


# Sets of cover types for classification
FORESTED_COVERS = frozenset({
    Cover.BROADLEAF_EVERGREEN, Cover.BROADLEAF_DECIDUOUS,
    Cover.BROADLEAF_DECIDUOUS_CLOSED, Cover.BROADLEAF_DECIDUOUS_OPEN,
    Cover.NEEDLEAF_EVERGREEN, Cover.NEEDLEAF_EVERGREEN_CLOSED,
    Cover.NEEDLEAF_EVERGREEN_OPEN, Cover.NEEDLEAF_DECIDUOUS,
    Cover.NEEDLEAF_DECIDUOUS_CLOSED, Cover.NEEDLEAF_DECIDUOUS_OPEN,
    Cover.MIXED_LEAF_TYPE,
    Cover.TREE_AND_SHRUB_WITH_HERBACEOUS_COVER,
    Cover.TREE_OR_SHRUB_COVER,
    Cover.FRESH_FLOODED_FOREST, Cover.SALINE_FLOODED_FOREST,
})

CLOSED_FOREST_COVERS = frozenset({
    Cover.BROADLEAF_DECIDUOUS_CLOSED,
    Cover.NEEDLEAF_EVERGREEN_CLOSED,
    Cover.NEEDLEAF_DECIDUOUS_CLOSED,
})

FLOODED_COVERS = frozenset({
    Cover.FRESH_FLOODED_FOREST,
    Cover.SALINE_FLOODED_FOREST,
    Cover.FLOODED_VEGETATION,
})

BARREN_COVERS = frozenset({
    Cover.BARE, Cover.BARE_CONSOLIDATED, Cover.BARE_UNCONSOLIDATED,
})

NEEDLEAF_COVERS = frozenset({
    Cover.NEEDLEAF_EVERGREEN, Cover.NEEDLEAF_EVERGREEN_CLOSED,
    Cover.NEEDLEAF_EVERGREEN_OPEN, Cover.NEEDLEAF_DECIDUOUS,
    Cover.NEEDLEAF_DECIDUOUS_CLOSED, Cover.NEEDLEAF_DECIDUOUS_OPEN,
})
