"""Soil predictor data sources using Terrarium soil rasters."""

import math

import numpy as np

from earth2mt.config import TILE_SIZE, SoilSuborder, soil_suborder_by_id
from earth2mt.data.elevation import (
    COSINE,
    LINEAR,
    NEAREST,
    _interpolate_1d,
    _select_interpolation_mode,
)
from earth2mt.data.raster_reader import read_raster
from earth2mt.data.tile_source import TileSource
from earth2mt.terrain.coords import (
    CoordinateTransform,
    best_zoom_for_scale,
    global_pixel_to_tile_pixel,
    meters_per_pixel,
)


ORGANIC_CARBON_ENDPOINT = "occ"
SOIL_CLASS_ENDPOINT = "usda"
SOIL_MAX_ZOOM = 4

DEFAULT_ORGANIC_CARBON_CONTENT = 10


class OrganicCarbonSource:
    def __init__(self, cache_dir: str, scale: float):
        self.tile_source = TileSource(cache_dir)
        self.zoom = best_zoom_for_scale(scale, SOIL_MAX_ZOOM)
        self.interpolation = _select_interpolation_mode(meters_per_pixel(self.zoom) / scale)
        self._tile_cache: dict[tuple[int, int], np.ndarray] = {}

    def get_tile(self, tile_x: int, tile_y: int) -> np.ndarray:
        key = (tile_x, tile_y)
        if key not in self._tile_cache:
            try:
                raw = self.tile_source.fetch_tile(
                    ORGANIC_CARBON_ENDPOINT, self.zoom, tile_x, tile_y
                )
                self._tile_cache[key] = read_raster(raw)
            except Exception:
                self._tile_cache[key] = np.full(
                    (TILE_SIZE, TILE_SIZE),
                    DEFAULT_ORGANIC_CARBON_CONTENT,
                    dtype=np.int16,
                )
        return self._tile_cache[key]

    def sample(self, coords: CoordinateTransform, bx: int, bz: int) -> int:
        lat, lon = coords.block_to_geo(bx, bz)
        global_px, global_py = coords.geo_to_global_pixel(lat, lon, self.zoom)
        return int(round(self._sample_global_pixel(global_px, global_py)))

    def clear_cache(self):
        self._tile_cache.clear()

    def _get_global_value(self, global_px: int, global_py: int) -> float:
        tile_x, tile_y, px, py = global_pixel_to_tile_pixel(global_px, global_py, self.zoom)
        tile = self.get_tile(tile_x, tile_y)
        return float(tile[py, px])

    def _sample_global_pixel(self, global_px: float, global_py: float) -> float:
        sample_x = global_px - 0.5
        sample_y = global_py - 0.5

        if self.interpolation == NEAREST:
            src_x = math.floor(sample_x)
            src_y = math.floor(sample_y)
            return self._get_global_value(src_x, src_y)

        origin_x = math.floor(sample_x)
        origin_y = math.floor(sample_y)
        frac_x = sample_x - origin_x
        frac_y = sample_y - origin_y

        if self.interpolation in (LINEAR, COSINE):
            kernel_width = 2
            kernel_offset = 0
        else:
            kernel_width = 4
            kernel_offset = -1

        columns = []
        for kernel_x in range(kernel_width):
            source_x = origin_x + kernel_x + kernel_offset
            column = []
            for kernel_y in range(kernel_width):
                source_y = origin_y + kernel_y + kernel_offset
                column.append(self._get_global_value(source_x, source_y))
            columns.append(_interpolate_1d(self.interpolation, column, frac_y))

        return _interpolate_1d(self.interpolation, columns, frac_x)


class SoilClassSource:
    def __init__(self, cache_dir: str, scale: float):
        self.tile_source = TileSource(cache_dir)
        self.zoom = best_zoom_for_scale(scale, SOIL_MAX_ZOOM)
        self._tile_cache: dict[tuple[int, int], np.ndarray] = {}

    def get_tile(self, tile_x: int, tile_y: int) -> np.ndarray:
        key = (tile_x, tile_y)
        if key not in self._tile_cache:
            try:
                raw = self.tile_source.fetch_tile(
                    SOIL_CLASS_ENDPOINT, self.zoom, tile_x, tile_y
                )
                self._tile_cache[key] = read_raster(raw)
            except Exception:
                self._tile_cache[key] = np.full(
                    (TILE_SIZE, TILE_SIZE),
                    SoilSuborder.NO.id,
                    dtype=np.uint8,
                )
        return self._tile_cache[key]

    def sample(self, coords: CoordinateTransform, bx: int, bz: int) -> SoilSuborder:
        lat, lon = coords.block_to_geo(bx, bz)
        tile_x, tile_y, px, py = coords.geo_to_tile_pixel(lat, lon, self.zoom)
        tile = self.get_tile(tile_x, tile_y)
        return soil_suborder_by_id(int(tile[py, px]))

    def clear_cache(self):
        self._tile_cache.clear()
