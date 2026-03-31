"""Terrarium-style soil texture selection and sampling."""

import hashlib
import math
import random
from dataclasses import dataclass

import numpy as np

from earth2mt.config import (
    BARREN_COVERS,
    CLAY,
    COARSE_DIRT,
    CONSOLIDATED_COVERS,
    DIRT,
    GRASS_BLOCK,
    GRAVEL,
    LIGHT_GRAY_TERRACOTTA,
    Landform,
    ORANGE_TERRACOTTA,
    PODZOL,
    RED_SAND,
    RED_SANDSTONE,
    RED_TERRACOTTA,
    SAND,
    SANDSTONE,
    SNOW_BLOCK,
    STONE,
    SoilOrder,
    SoilSuborder,
    TERRACOTTA,
    WHITE_TERRACOTTA,
    YELLOW_TERRACOTTA,
    BROWN_TERRACOTTA,
    Cover,
)


VERY_GRASSY_OCC = 40
GRASSY_OCC = 9

SURFACE_RANDOM_SEED = 6035435416693430887
PATCH_NOISE_SEED = 54321
MESA_NOISE_SEED = 1521

SANDY_SUBORDERS = frozenset({
    SoilSuborder.PSAMMENTS,
    SoilSuborder.SALIDS,
    SoilSuborder.ARENTS,
    SoilSuborder.ARGIDS,
    SoilSuborder.CAMBIDS,
    SoilSuborder.USTEPTS,
    SoilSuborder.USTOX,
    SoilSuborder.XEREPTS,
    SoilSuborder.XEROLLS,
    SoilSuborder.XERALFS,
    SoilSuborder.XERANDS,
})


@dataclass(slots=True)
class GrowthPredictors:
    annual_rainfall: float
    organic_carbon_content: int
    slope: int
    cover: Cover
    soil_suborder: SoilSuborder
    landform: Landform


class HomogenousTexture:
    def __init__(self, block: str):
        self.block = block

    def sample(self, rng: random.Random, x: int, y: int, z: int, slope: int, depth: int) -> str:
        return self.block


class GrassTexture:
    def __init__(self, grass_block: str):
        self.grass_block = grass_block

    def sample(self, rng: random.Random, x: int, y: int, z: int, slope: int, depth: int) -> str:
        if slope >= 60:
            return STONE
        return self.grass_block if depth == 0 else DIRT


class SandTexture:
    def __init__(self, sand_block: str, sandstone_block: str):
        self.sand_block = sand_block
        self.sandstone_block = sandstone_block

    def sample(self, rng: random.Random, x: int, y: int, z: int, slope: int, depth: int) -> str:
        if slope >= 60:
            return STONE
        if slope >= 30:
            return self.sandstone_block
        return self.sand_block


class SnowTexture:
    def sample(self, rng: random.Random, x: int, y: int, z: int, slope: int, depth: int) -> str:
        if slope >= 40:
            return STONE
        return SNOW_BLOCK


class BinaryPatchesTexture:
    def __init__(self, a, b, bias: float):
        self.a = a
        self.b = b
        self.bias = bias

    def sample(self, rng: random.Random, x: int, y: int, z: int, slope: int, depth: int) -> str:
        noise = _perlin_noise(x, z, scale=1.0 / 24.0, seed=PATCH_NOISE_SEED)
        noise += (rng.random() - rng.random()) * 0.4
        if noise > self.bias:
            return self.a.sample(rng, x, y, z, slope, depth)
        return self.b.sample(rng, x, y, z, slope, depth)


class ScatterTexture:
    def __init__(self, a, b, bias: float):
        self.a = a
        self.b = b
        self.remapped_bias = (bias + 1.0) / 2.0

    def sample(self, rng: random.Random, x: int, y: int, z: int, slope: int, depth: int) -> str:
        if rng.random() > self.remapped_bias:
            return self.a.sample(rng, x, y, z, slope, depth)
        return self.b.sample(rng, x, y, z, slope, depth)


class MesaSoilTexture:
    BAND_COUNT = 64

    def __init__(self):
        self.bands = self._generate_bands(random.Random(MESA_NOISE_SEED))

    def _generate_bands(self, rng: random.Random) -> list[str]:
        bands = [TERRACOTTA] * self.BAND_COUNT

        idx = 0
        while idx < self.BAND_COUNT:
            idx += rng.randint(1, 5)
            if idx < self.BAND_COUNT:
                bands[idx] = ORANGE_TERRACOTTA
            idx += 1

        self._add_single_bands(bands, rng, 1, YELLOW_TERRACOTTA)
        self._add_single_bands(bands, rng, 2, BROWN_TERRACOTTA)
        self._add_single_bands(bands, rng, 1, RED_TERRACOTTA)
        self._add_gradient_bands(bands, rng, WHITE_TERRACOTTA, LIGHT_GRAY_TERRACOTTA)

        return bands

    def _add_single_bands(self, bands: list[str], rng: random.Random, min_depth: int, block: str):
        count = rng.randint(2, 5)
        for _ in range(count):
            depth = rng.randint(min_depth, min_depth + 2)
            start = rng.randrange(self.BAND_COUNT)
            for offset in range(depth):
                band_y = start + offset
                if band_y >= self.BAND_COUNT:
                    break
                bands[band_y] = block

    def _add_gradient_bands(self, bands: list[str], rng: random.Random, main: str, fade: str):
        count = rng.randint(3, 5)
        band_y = 0
        for _ in range(count):
            band_y += rng.randint(4, 19)
            if band_y >= self.BAND_COUNT:
                break

            bands[band_y] = main
            if band_y > 1 and rng.random() < 0.5:
                bands[band_y - 1] = fade
            if band_y < self.BAND_COUNT - 1 and rng.random() < 0.5:
                bands[band_y + 1] = fade

    def sample(self, rng: random.Random, x: int, y: int, z: int, slope: int, depth: int) -> str:
        noise = _perlin_noise(x, z, scale=1.0 / 512.0, seed=MESA_NOISE_SEED)
        offset = round(noise * 2.0)
        return self.bands[(y + offset + self.BAND_COUNT) % self.BAND_COUNT]


GRASS_TEXTURE = GrassTexture(GRASS_BLOCK)
PODZOL_TEXTURE = GrassTexture(PODZOL)
CLAY_TEXTURE = HomogenousTexture(CLAY)
COARSE_DIRT_TEXTURE = GrassTexture(COARSE_DIRT)

DESERT_SAND_TEXTURE = SandTexture(SAND, SANDSTONE)
DESERT_RED_SAND_TEXTURE = SandTexture(RED_SAND, RED_SANDSTONE)

SAND_TEXTURE = ScatterTexture(DESERT_SAND_TEXTURE, GRASS_TEXTURE, -0.5)
RED_SAND_TEXTURE = ScatterTexture(DESERT_RED_SAND_TEXTURE, GRASS_TEXTURE, -0.5)

ROCK_TEXTURE = HomogenousTexture(STONE)
SNOW_TEXTURE = SnowTexture()
MESA_TEXTURE = MesaSoilTexture()

BEACH_TEXTURE = HomogenousTexture(SAND)
RIVER_BED_TEXTURE = BinaryPatchesTexture(HomogenousTexture(DIRT), CLAY_TEXTURE, -0.5)
OCEAN_FLOOR_TEXTURE = HomogenousTexture(GRAVEL)

GRASS_AND_DIRT_TEXTURE = BinaryPatchesTexture(GRASS_TEXTURE, COARSE_DIRT_TEXTURE, -0.2)
GRASS_AND_SAND_TEXTURE = BinaryPatchesTexture(GRASS_TEXTURE, DESERT_SAND_TEXTURE, -0.2)
GRASS_AND_PODZOL_TEXTURE = BinaryPatchesTexture(GRASS_TEXTURE, PODZOL_TEXTURE, -0.2)


def _noise(x: int, z: int, seed: int) -> float:
    digest = hashlib.blake2b(f"{x}:{z}:{seed}".encode("ascii"), digest_size=16).digest()
    value = int.from_bytes(digest[:8], "big") / float(1 << 64)
    return value * 2.0 - 1.0


def _perlin_noise(x: int, z: int, scale: float, seed: int) -> float:
    sx = x * scale
    sz = z * scale
    ix = math.floor(sx)
    iz = math.floor(sz)
    fx = sx - ix
    fz = sz - iz

    fx = fx * fx * (3.0 - 2.0 * fx)
    fz = fz * fz * (3.0 - 2.0 * fz)

    n00 = _noise(ix, iz, seed)
    n10 = _noise(ix + 1, iz, seed)
    n01 = _noise(ix, iz + 1, seed)
    n11 = _noise(ix + 1, iz + 1, seed)

    nx0 = n00 + fx * (n10 - n00)
    nx1 = n01 + fx * (n11 - n01)
    return nx0 + fz * (nx1 - nx0)


def _depth_noise(x: int, z: int) -> float:
    total = 0.0
    for octave in range(4):
        total += _perlin_noise(
            x,
            z,
            scale=0.0625 * (2 ** octave),
            seed=PATCH_NOISE_SEED + octave,
        )
    return max(0.0, min(1.0, (total + 4.0) / 8.0))


def _very_dry(annual_rainfall: float) -> bool:
    return annual_rainfall < 380.0


def _is_sandy(suborder: SoilSuborder) -> bool:
    return suborder in SANDY_SUBORDERS


def compute_slope(elevations: np.ndarray, x: int, z: int, height_scale: float) -> int:
    current = float(elevations[z, x])
    rises = (
        (current - float(elevations[z - 1, x - 1])) * height_scale,
        (current - float(elevations[z - 1, x + 1])) * height_scale,
        (current - float(elevations[z + 1, x - 1])) * height_scale,
        (current - float(elevations[z + 1, x + 1])) * height_scale,
    )
    max_slope = max(math.degrees(math.atan(abs(rise))) for rise in rises)
    return math.floor(max_slope)


def select_soil_texture(predictors: GrowthPredictors):
    if predictors.landform == Landform.SEA:
        return OCEAN_FLOOR_TEXTURE
    if predictors.landform == Landform.BEACH:
        return BEACH_TEXTURE
    if predictors.landform == Landform.LAKE_OR_RIVER:
        return RIVER_BED_TEXTURE

    if predictors.cover == Cover.PERMANENT_SNOW or predictors.soil_suborder == SoilSuborder.ICE:
        return SNOW_TEXTURE

    if predictors.soil_suborder == SoilSuborder.ROCK:
        return ROCK_TEXTURE
    if predictors.soil_suborder == SoilSuborder.SHIFTING_SAND:
        return SAND_TEXTURE

    texture = _select_land_texture(predictors)

    if predictors.cover in CONSOLIDATED_COVERS:
        texture = _consolidate(texture)

    if predictors.soil_suborder.order == SoilOrder.SPODOSOL and texture is GRASS_TEXTURE:
        texture = GRASS_AND_PODZOL_TEXTURE

    if predictors.cover in BARREN_COVERS:
        if texture is SAND_TEXTURE:
            return DESERT_SAND_TEXTURE
        if texture is RED_SAND_TEXTURE:
            return DESERT_RED_SAND_TEXTURE

    return texture


def _select_land_texture(predictors: GrowthPredictors):
    if predictors.organic_carbon_content > VERY_GRASSY_OCC:
        return GRASS_TEXTURE

    grassy = (
        predictors.organic_carbon_content > GRASSY_OCC
        and not _very_dry(predictors.annual_rainfall)
    )

    if grassy:
        return _select_grassy_texture(predictors)
    return _select_not_grassy_texture(predictors)


def _select_grassy_texture(predictors: GrowthPredictors):
    if _is_sandy(predictors.soil_suborder):
        return GRASS_AND_SAND_TEXTURE
    return GRASS_TEXTURE


def _select_not_grassy_texture(predictors: GrowthPredictors):
    sandy = _is_sandy(predictors.soil_suborder)

    if predictors.soil_suborder == SoilSuborder.ORTHENTS:
        if predictors.slope <= 50:
            return SAND_TEXTURE
        return MESA_TEXTURE

    if sandy:
        return SAND_TEXTURE
    return GRASS_AND_DIRT_TEXTURE


def _consolidate(texture):
    if texture is SAND_TEXTURE:
        return MESA_TEXTURE
    return ROCK_TEXTURE


def _column_seed(world_seed: int, x: int, cube_min_y: int, z: int) -> int:
    payload = f"{world_seed}:{SURFACE_RANDOM_SEED}:{x}:{cube_min_y}:{z}".encode("ascii")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


def sample_soil_profile(texture, world_seed: int, x: int, surface_y: int, z: int, slope: int) -> list[str]:
    cube_min_y = (surface_y // 16) * 16
    rng = random.Random(_column_seed(world_seed, x, cube_min_y, z))
    soil_depth = math.floor(1.5 + rng.random() * 0.25 + _depth_noise(x, z) * 1.5)
    soil_depth = max(1, soil_depth)

    layers = []
    for depth in range(soil_depth):
        y = surface_y - depth
        layers.append(texture.sample(rng, x, y, z, slope, depth))
    return layers
