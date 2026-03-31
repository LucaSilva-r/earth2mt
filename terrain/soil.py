"""Soil texture and surface block selection - port of Terrarium's SoilTextures/SoilSelector.

Maps biomes to surface blocks (top layer + subsurface layers).
"""

import math
import hashlib
from earth2mt.config import (
    Biome,
    STONE, DIRT, GRASS_BLOCK, PODZOL, COARSE_DIRT,
    SAND, RED_SAND, SANDSTONE, RED_SANDSTONE,
    GRAVEL, CLAY, SNOW_BLOCK, ICE,
    MAX_SOIL_DEPTH,
)


def _noise(x: int, z: int, seed: int = 54321) -> float:
    """Simple deterministic noise in [-1, 1] for soil variation."""
    h = hashlib.md5(f"{x}:{z}:{seed}".encode()).digest()
    return (h[0] / 127.5) - 1.0


def _perlin_noise(x: int, z: int, scale: float = 0.0625, seed: int = 54321) -> float:
    """Simplified perlin-like noise using hash mixing at multiple octaves."""
    sx = x * scale
    sz = z * scale
    ix, iz = int(math.floor(sx)), int(math.floor(sz))
    fx, fz = sx - ix, sz - iz

    # Smooth interpolation
    fx = fx * fx * (3 - 2 * fx)
    fz = fz * fz * (3 - 2 * fz)

    n00 = _noise(ix, iz, seed)
    n10 = _noise(ix + 1, iz, seed)
    n01 = _noise(ix, iz + 1, seed)
    n11 = _noise(ix + 1, iz + 1, seed)

    nx0 = n00 + fx * (n10 - n00)
    nx1 = n01 + fx * (n11 - n01)

    return nx0 + fz * (nx1 - nx0)


def soil_depth(x: int, z: int) -> int:
    """Calculate soil depth at a position (1-6 blocks)."""
    depth_noise = _perlin_noise(x, z)
    depth = int(1.5 + depth_noise * 1.5)
    return max(1, min(MAX_SOIL_DEPTH, depth))


def select_surface_blocks(biome: Biome, x: int, z: int) -> tuple[str, str]:
    """Select (top_block, sub_block) for a given biome and position.

    Returns the block to place at the surface (top) and the block for
    subsurface soil layers (sub).
    """
    noise = _perlin_noise(x, z, scale=1 / 24.0, seed=12345)

    if biome == Biome.DEEP_OCEAN or biome == Biome.OCEAN:
        return GRAVEL, GRAVEL

    if biome == Biome.RIVER or biome == Biome.FROZEN_RIVER:
        # Dirt/clay patches
        if noise > -0.5:
            return DIRT, DIRT
        return CLAY, CLAY

    if biome == Biome.BEACH or biome == Biome.COLD_BEACH:
        return SAND, SAND

    if biome == Biome.ICE_PLAINS:
        return SNOW_BLOCK, SNOW_BLOCK

    if biome == Biome.DESERT:
        return SAND, SAND

    if biome == Biome.SAVANNA:
        # Grass with coarse dirt patches
        if noise < -0.2:
            return COARSE_DIRT, DIRT
        return GRASS_BLOCK, DIRT

    if biome == Biome.COLD_TAIGA:
        # Podzol/grass mix
        if noise < -0.2:
            return PODZOL, DIRT
        return GRASS_BLOCK, DIRT

    if biome == Biome.TAIGA:
        # Podzol in needleaf areas
        if noise < -0.2:
            return PODZOL, DIRT
        return GRASS_BLOCK, DIRT

    if biome == Biome.SWAMPLAND:
        return GRASS_BLOCK, DIRT

    if biome in (Biome.JUNGLE, Biome.JUNGLE_EDGE):
        return GRASS_BLOCK, DIRT

    if biome == Biome.ROOFED_FOREST:
        return GRASS_BLOCK, DIRT

    if biome == Biome.FOREST:
        return GRASS_BLOCK, DIRT

    if biome == Biome.BIRCH_FOREST:
        return GRASS_BLOCK, DIRT

    # PLAINS and default
    return GRASS_BLOCK, DIRT
