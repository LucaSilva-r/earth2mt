"""Biome classification - port of Terrarium's StandardBiomeClassifier.java."""

from earth2mt.config import (
    Biome, Landform, Cover,
    FORESTED_COVERS, CLOSED_FOREST_COVERS, FLOODED_COVERS, BARREN_COVERS,
    NEEDLEAF_COVERS,
    MIN_FREEZE_TEMP, MEAN_COLD_TEMP,
    DESERT_RAINFALL, VERY_DRY_RAINFALL, DRY_RAINFALL,
    RAINFOREST_RAINFALL, TAIGA_MIN_TEMP, TAIGA_MAX_TEMP, TROPICAL_RF_MIN_TEMP,
)


def is_frozen(min_temp: float, mean_temp: float) -> bool:
    return min_temp < MIN_FREEZE_TEMP and mean_temp < MEAN_COLD_TEMP


def has_frozen_cover(cover: Cover) -> bool:
    return cover == Cover.PERMANENT_SNOW


def is_effectively_frozen(cover: Cover, min_temp: float, mean_temp: float) -> bool:
    return has_frozen_cover(cover) or is_frozen(min_temp, mean_temp)


def is_cold(cover: Cover, min_temp: float, mean_temp: float) -> bool:
    return mean_temp < MEAN_COLD_TEMP or is_effectively_frozen(cover, min_temp, mean_temp)


def is_desert(rainfall: float) -> bool:
    return rainfall < DESERT_RAINFALL


def is_dry(rainfall: float) -> bool:
    return rainfall < DRY_RAINFALL


def is_tropical_rainforest(rainfall: float, mean_temp: float) -> bool:
    return rainfall >= RAINFOREST_RAINFALL and mean_temp >= TROPICAL_RF_MIN_TEMP


def is_taiga(rainfall: float, mean_temp: float) -> bool:
    return rainfall >= VERY_DRY_RAINFALL and TAIGA_MIN_TEMP <= mean_temp <= TAIGA_MAX_TEMP


def is_forested(cover: Cover) -> bool:
    return cover in FORESTED_COVERS


def is_flooded(cover: Cover) -> bool:
    return cover in FLOODED_COVERS


def is_barren(cover: Cover) -> bool:
    return cover in BARREN_COVERS


def determine_landform(cover: Cover, elevation: float) -> Landform:
    """Simplified landform determination from cover type and elevation."""
    if cover == Cover.WATER:
        if elevation < -10:
            return Landform.SEA
        else:
            return Landform.LAKE_OR_RIVER
    return Landform.LAND


def classify_biome(
    elevation: float,
    cover: Cover,
    mean_temp: float,
    min_temp: float,
    rainfall: float,
) -> Biome:
    """Classify a location into a biome based on geographic data.

    Port of Terrarium's StandardBiomeClassifier.java.
    """
    if elevation == -32768 or elevation < -9999:
        return Biome.VOID

    landform = determine_landform(cover, elevation)

    if landform != Landform.LAND:
        return _classify_water(landform, cover, elevation, min_temp, mean_temp)

    return _classify_land(cover, elevation, mean_temp, min_temp, rainfall)


def _classify_water(
    landform: Landform,
    cover: Cover,
    elevation: float,
    min_temp: float,
    mean_temp: float,
) -> Biome:
    if landform == Landform.SEA:
        if elevation < -500:
            return Biome.DEEP_OCEAN
        return Biome.OCEAN

    # Lake or river
    if is_effectively_frozen(cover, min_temp, mean_temp):
        return Biome.FROZEN_RIVER
    return Biome.RIVER


def _classify_land(
    cover: Cover,
    elevation: float,
    mean_temp: float,
    min_temp: float,
    rainfall: float,
) -> Biome:
    # Beach detection: low elevation near sea level, non-water
    if elevation >= -2 and elevation <= 3:
        if is_effectively_frozen(cover, min_temp, mean_temp):
            return Biome.COLD_BEACH
        return Biome.BEACH

    # Frozen biomes
    if is_effectively_frozen(cover, min_temp, mean_temp):
        return Biome.COLD_TAIGA if is_forested(cover) else Biome.ICE_PLAINS

    # Flooded areas
    if is_flooded(cover):
        if cover == Cover.SALINE_FLOODED_FOREST:
            return Biome.SWAMPLAND
        return Biome.JUNGLE if is_forested(cover) else Biome.JUNGLE_EDGE

    # Desert
    if is_desert(rainfall) and not is_forested(cover):
        return Biome.DESERT

    # Only check tropical/taiga if not barren
    if not is_barren(cover):
        if is_tropical_rainforest(rainfall, mean_temp):
            return Biome.JUNGLE if is_forested(cover) else Biome.JUNGLE_EDGE

        if is_taiga(rainfall, mean_temp) and is_forested(cover):
            return Biome.TAIGA

    # Non-specific selection
    if is_cold(cover, min_temp, mean_temp):
        return Biome.TAIGA
    elif is_dry(rainfall):
        return Biome.SAVANNA

    if is_forested(cover):
        return _classify_forest(cover)

    return Biome.PLAINS


def _classify_forest(cover: Cover) -> Biome:
    """Classify forest type based on cover."""
    # Needleleaf forests -> approximate as birch forest (boreal feel)
    if cover in NEEDLEAF_COVERS:
        return Biome.TAIGA

    # Closed broadleaf -> roofed forest
    if cover in CLOSED_FOREST_COVERS:
        return Biome.ROOFED_FOREST

    return Biome.FOREST
