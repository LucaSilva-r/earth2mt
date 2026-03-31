"""Coordinate transforms between geographic (lat/lon), block, and tile coordinates."""

import math
from earth2mt.config import EQUATOR_CIRCUMFERENCE, TILE_SIZE, ZOOM_BASE


def tile_count_x(zoom: int) -> float:
    return tile_count_y(zoom) * 2.0


def tile_count_y(zoom: int) -> float:
    return ZOOM_BASE ** zoom


def global_width(zoom: int) -> float:
    return tile_count_x(zoom) * TILE_SIZE


def global_height(zoom: int) -> float:
    return tile_count_y(zoom) * TILE_SIZE


def global_pixel_to_tile_pixel(global_px: float, global_py: float, zoom: int) -> tuple[int, int, int, int]:
    """Convert global pixel coordinates to (tile_x, tile_y, pixel_x, pixel_y)."""
    max_px = global_width(zoom) - 1.0
    max_py = global_height(zoom) - 1.0

    global_px = max(0.0, min(global_px, max_px))
    global_py = max(0.0, min(global_py, max_py))

    tile_x = int(global_px // TILE_SIZE)
    tile_y = int(global_py // TILE_SIZE)
    pixel_x = int(global_px % TILE_SIZE)
    pixel_y = int(global_py % TILE_SIZE)

    return tile_x, tile_y, pixel_x, pixel_y


def meters_per_pixel(zoom: int) -> float:
    return EQUATOR_CIRCUMFERENCE / global_width(zoom)


def best_zoom_for_scale(scale: float, max_zoom: int) -> int:
    """Pick the Terrarium zoom level that best matches the world scale."""
    zoom = math.log(EQUATOR_CIRCUMFERENCE / (2.0 * TILE_SIZE * scale), ZOOM_BASE)
    return max(0, min(max_zoom, int(round(zoom))))


class CoordinateTransform:
    """Converts between geographic coordinates, block coordinates, and tile pixel coordinates.

    Block coordinate (0, 0) corresponds to (center_lat, center_lon).
    In Luanti: +X = east, +Z = south (matching Terrarium's convention).
    """

    def __init__(self, center_lat: float, center_lon: float, scale: float):
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.scale = scale  # meters per block

        center_lat_radians = math.radians(center_lat)
        # Longitude degrees shrink toward the poles; use the local scale at the
        # world center so east/west distances stay consistent for small regions.
        self.meters_per_deg_lon = (EQUATOR_CIRCUMFERENCE * math.cos(center_lat_radians)) / 360.0
        self.meters_per_deg_lat = EQUATOR_CIRCUMFERENCE / 360.0  # local approximation

    def block_to_geo(self, bx: int, bz: int) -> tuple[float, float]:
        """Convert block coordinates to (lat, lon)."""
        # +X = east, +Z = south
        east_meters = bx * self.scale
        south_meters = bz * self.scale

        lon = self.center_lon + east_meters / self.meters_per_deg_lon
        lat = self.center_lat - south_meters / self.meters_per_deg_lat

        return lat, lon

    def geo_to_block(self, lat: float, lon: float) -> tuple[int, int]:
        """Convert (lat, lon) to block coordinates."""
        east_meters = (lon - self.center_lon) * self.meters_per_deg_lon
        south_meters = (self.center_lat - lat) * self.meters_per_deg_lat

        bx = int(round(east_meters / self.scale))
        bz = int(round(south_meters / self.scale))

        return bx, bz

    def elevation_to_world_y(self, elevation_meters: float, sea_level: int = 0) -> int:
        """Convert a real-world elevation in meters to a Luanti Y coordinate.

        `self.scale` is expressed in meters per block, so it applies vertically
        as well as horizontally. Sea level remains at the requested Y offset.
        """
        return int(round(elevation_meters / self.scale)) + sea_level

    def geo_to_global_pixel(self, lat: float, lon: float, zoom: int) -> tuple[float, float]:
        """Convert (lat, lon) to floating-point global pixel coordinates."""
        tc_x = tile_count_x(zoom)
        tc_y = tile_count_y(zoom)

        norm_lon = (lon + 180.0) / 360.0
        norm_lat = (90.0 - lat) / 180.0

        global_px = norm_lon * tc_x * TILE_SIZE
        global_py = norm_lat * tc_y * TILE_SIZE

        max_px = global_width(zoom) - 1.0
        max_py = global_height(zoom) - 1.0
        global_px = max(0.0, min(global_px, max_px))
        global_py = max(0.0, min(global_py, max_py))

        return global_px, global_py

    def geo_to_tile_pixel(self, lat: float, lon: float, zoom: int) -> tuple[int, int, int, int]:
        """Convert (lat, lon) to (tile_x, tile_y, pixel_x, pixel_y) in the tile grid.

        The tile grid covers the whole globe:
        - tile_x: 0..tile_count_x-1, left (lon=-180) to right (lon=+180)
        - tile_y: 0..tile_count_y-1, top (lat=+90) to bottom (lat=-90)
        """
        global_px, global_py = self.geo_to_global_pixel(lat, lon, zoom)
        return global_pixel_to_tile_pixel(global_px, global_py, zoom)

    def block_to_tile_pixel(self, bx: int, bz: int, zoom: int) -> tuple[int, int, int, int]:
        """Convert block coordinates to tile + pixel coordinates."""
        lat, lon = self.block_to_geo(bx, bz)
        return self.geo_to_tile_pixel(lat, lon, zoom)
