"""Mineclonia biome mapping and biome-index encoding helpers."""

from collections import Counter

from earth2mt.config import (
    Biome,
    CLOSED_FOREST_COVERS,
    Cover,
    GRASS_BLOCK,
    GRASS_BLOCK_SNOW,
    MEAN_COLD_TEMP,
    MEAN_HOT_TEMP,
    MEAN_WARM_TEMP,
    NEEDLEAF_COVERS,
    PODZOL,
    PODZOL_SNOW,
    RED_SAND,
    RED_SANDSTONE,
    TERRACOTTA,
)
from earth2mt.terrain.biome import is_effectively_frozen, is_forested
from earth2mt.terrain.soil import DESERT_RED_SAND_TEXTURE, MESA_TEXTURE, RED_SAND_TEXTURE

MINECLONIA_BIOME_METADATA_KEY = "mcl_levelgen:biome_index"
DEFAULT_MINECLONIA_BIOME = "Plains"

MINECLONIA_BIOME_NAMES = (
    "Ocean",
    "DeepOcean",
    "ColdOcean",
    "DeepColdOcean",
    "LukewarmOcean",
    "DeepLukewarmOcean",
    "WarmOcean",
    "FrozenOcean",
    "DeepFrozenOcean",
    "River",
    "FrozenRiver",
    "Beach",
    "SnowyBeach",
    "StonyShore",
    "SnowyPlains",
    "SnowyTaiga",
    "Swamp",
    "MangroveSwamp",
    "Jungle",
    "SparseJungle",
    "Desert",
    "Taiga",
    "Savannah",
    "DarkForest",
    "Forest",
    "BirchForest",
    "Plains",
    "Mesa",
    "WoodedMesa",
)

MINECLONIA_BIOME_IDS = {
    biome_name: biome_id
    for biome_id, biome_name in enumerate(MINECLONIA_BIOME_NAMES, start=1)
}

# Palette indices mirror Mineclonia's current mcl_levelgen biome definitions.
MINECLONIA_GRASS_PALETTE_INDICES = {
    "Ocean": 0,
    "DeepOcean": 0,
    "ColdOcean": 0,
    "DeepColdOcean": 0,
    "LukewarmOcean": 0,
    "DeepLukewarmOcean": 0,
    "WarmOcean": 0,
    "FrozenOcean": 2,
    "DeepFrozenOcean": 0,
    "River": 0,
    "FrozenRiver": 2,
    "Beach": 0,
    "SnowyBeach": 32,
    "StonyShore": 34,
    "SnowyPlains": 10,
    "SnowyTaiga": 10,
    "Swamp": 28,
    "MangroveSwamp": 27,
    "Jungle": 24,
    "SparseJungle": 26,
    "Desert": 17,
    "Taiga": 12,
    "Savannah": 1,
    "DarkForest": 18,
    "Forest": 13,
    "BirchForest": 15,
    "Plains": 11,
    "Mesa": 19,
    "WoodedMesa": 19,
}

MINECLONIA_LEAVES_PALETTE_INDICES = dict(MINECLONIA_GRASS_PALETTE_INDICES)
MINECLONIA_LEAVES_PALETTE_INDICES.update({
    "SnowyBeach": 31,
    "StonyShore": 31,
    "Mesa": 11,
    "WoodedMesa": 11,
})

PALETTE_NODES = frozenset({
    GRASS_BLOCK,
    GRASS_BLOCK_SNOW,
    PODZOL,
    PODZOL_SNOW,
})

_MESA_SURFACE_NODES = frozenset({
    RED_SAND,
    RED_SANDSTONE,
    TERRACOTTA,
})


def get_mineclonia_biome_id(biome_name: str) -> int:
    return MINECLONIA_BIOME_IDS[biome_name]


def get_grass_palette_index(biome_name: str) -> int:
    return MINECLONIA_GRASS_PALETTE_INDICES.get(biome_name, 0)


def get_leaves_palette_index(biome_name: str) -> int:
    return MINECLONIA_LEAVES_PALETTE_INDICES.get(biome_name, 0)


def classify_mineclonia_biome(
    biome: Biome,
    cover: Cover,
    mean_temp: float,
    min_temp: float,
    soil_texture,
    has_surface_snow: bool,
    surface_block: str | None,
) -> str:
    """Map earth2mt's Terrarium-style biome classification to Mineclonia biomes."""
    frozen = is_effectively_frozen(cover, min_temp, mean_temp)
    snowy = frozen or has_surface_snow
    forested = is_forested(cover)
    mesa = _is_mesa_biome(soil_texture, surface_block)

    if biome == Biome.DEEP_OCEAN:
        return _classify_ocean(mean_temp, min_temp, deep=True)
    if biome == Biome.OCEAN:
        return _classify_ocean(mean_temp, min_temp, deep=False)
    if biome == Biome.FROZEN_RIVER or (biome == Biome.RIVER and frozen):
        return "FrozenRiver"
    if biome == Biome.RIVER:
        return "River"
    if biome in (Biome.BEACH, Biome.COLD_BEACH):
        if snowy:
            return "SnowyBeach"
        return "Beach"
    if biome == Biome.COLD_TAIGA:
        return "SnowyTaiga"
    if biome == Biome.ICE_PLAINS:
        return "SnowyPlains"
    if biome == Biome.SWAMPLAND:
        if cover == Cover.SALINE_FLOODED_FOREST:
            return "MangroveSwamp"
        return "Swamp"
    if biome == Biome.JUNGLE:
        return "Jungle" if forested else "SparseJungle"
    if biome == Biome.JUNGLE_EDGE:
        return "SparseJungle"
    if biome == Biome.DESERT:
        if mesa:
            return "WoodedMesa" if forested else "Mesa"
        return "Desert"
    if biome == Biome.TAIGA:
        if snowy:
            return "SnowyTaiga" if forested else "SnowyPlains"
        return "Taiga" if forested else "Plains"
    if biome == Biome.SAVANNA:
        return "Savannah"
    if biome == Biome.ROOFED_FOREST:
        return "DarkForest"
    if biome == Biome.BIRCH_FOREST:
        return "BirchForest"
    if biome == Biome.FOREST:
        return _classify_forest_biome(cover, snowy)
    if biome == Biome.PLAINS:
        if mesa:
            return "WoodedMesa" if forested else "Mesa"
        if snowy:
            return "SnowyPlains"
        if forested:
            return _classify_forest_biome(cover, snowy)
        return "Plains"
    return DEFAULT_MINECLONIA_BIOME


def encode_mapblock_biome_index(column_biome_ids) -> bytes:
    """Encode a 16x16 column of biome IDs into Mineclonia's quart-index RLE format."""
    quart_biomes: list[int] = []
    for qx in range(4):
        x0 = qx * 4
        for _qy in range(4):
            for qz in range(4):
                z0 = qz * 4
                quart_biomes.append(_mode_biome_id(column_biome_ids[z0:z0 + 4, x0:x0 + 4]))
    return _encode_run_lengths(quart_biomes)


def _classify_ocean(mean_temp: float, min_temp: float, deep: bool) -> str:
    if min_temp < 0.0 or mean_temp <= 0.0:
        return "DeepFrozenOcean" if deep else "FrozenOcean"
    if mean_temp >= MEAN_HOT_TEMP:
        return "WarmOcean"
    if mean_temp >= MEAN_WARM_TEMP:
        return "DeepLukewarmOcean" if deep else "LukewarmOcean"
    if mean_temp <= MEAN_COLD_TEMP:
        return "DeepColdOcean" if deep else "ColdOcean"
    return "DeepOcean" if deep else "Ocean"


def _classify_forest_biome(cover: Cover, snowy: bool) -> str:
    if cover in NEEDLEAF_COVERS:
        return "SnowyTaiga" if snowy else "Taiga"
    if cover in CLOSED_FOREST_COVERS:
        return "DarkForest"
    if snowy:
        return "SnowyTaiga"
    return "Forest"


def _is_mesa_biome(soil_texture, surface_block: str | None) -> bool:
    return (
        soil_texture in {MESA_TEXTURE, RED_SAND_TEXTURE, DESERT_RED_SAND_TEXTURE}
        or surface_block in _MESA_SURFACE_NODES
    )


def _mode_biome_id(window) -> int:
    counts = Counter(int(biome_id) for row in window for biome_id in row)
    return min(counts, key=lambda biome_id: (-counts[biome_id], biome_id))


def _encode_run_lengths(biome_ids: list[int]) -> bytes:
    if not biome_ids:
        return b""

    encoded = bytearray()
    run_length = 1
    current = biome_ids[0]
    for biome_id in biome_ids[1:]:
        if biome_id == current and run_length < 255:
            run_length += 1
            continue
        encoded.extend((run_length, current))
        current = biome_id
        run_length = 1
    encoded.extend((run_length, current))
    return bytes(encoded)
