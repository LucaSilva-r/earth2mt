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


def meters_per_pixel(zoom: int) -> float:
    return EQUATOR_CIRCUMFERENCE / global_width(zoom)


def best_zoom_for_scale(scale: float, max_zoom: int) -> int:
    """Pick the highest zoom level available (finest resolution).

    The Terrarium tile server has a max resolution of ~27.5 m/pixel at zoom 6.
    At 1 m/block scale, multiple blocks will map to the same pixel — that's expected.
    We always want the finest available data.
    """
    return max_zoom


class CoordinateTransform:
    """Converts between geographic coordinates, block coordinates, and tile pixel coordinates.

    Block coordinate (0, 0) corresponds to (center_lat, center_lon).
    In Luanti: +X = east, +Z = south (matching Terrarium's convention).
    """

    def __init__(self, center_lat: float, center_lon: float, scale: float):
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.scale = scale  # meters per block

        # Meters per degree at the equator
        self.meters_per_deg_lon = EQUATOR_CIRCUMFERENCE / 360.0
        # Adjust for latitude (longitude degrees shrink toward poles)
        self.meters_per_deg_lat = EQUATOR_CIRCUMFERENCE / 360.0  # approximate

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

    def geo_to_tile_pixel(self, lat: float, lon: float, zoom: int) -> tuple[int, int, int, int]:
        """Convert (lat, lon) to (tile_x, tile_y, pixel_x, pixel_y) in the tile grid.

        The tile grid covers the whole globe:
        - tile_x: 0..tile_count_x-1, left (lon=-180) to right (lon=+180)
        - tile_y: 0..tile_count_y-1, top (lat=+90) to bottom (lat=-90)
        """
        tc_x = tile_count_x(zoom)
        tc_y = tile_count_y(zoom)

        # Normalize longitude to 0..360, then to pixel x
        norm_lon = (lon + 180.0) / 360.0  # 0..1
        global_px = norm_lon * tc_x * TILE_SIZE

        # Normalize latitude to 0..1 (90 -> 0, -90 -> 1)
        norm_lat = (90.0 - lat) / 180.0  # 0..1
        global_py = norm_lat * tc_y * TILE_SIZE

        tile_x = int(global_px // TILE_SIZE)
        tile_y = int(global_py // TILE_SIZE)
        pixel_x = int(global_px % TILE_SIZE)
        pixel_y = int(global_py % TILE_SIZE)

        # Clamp
        tile_x = max(0, min(tile_x, int(tc_x) - 1))
        tile_y = max(0, min(tile_y, int(tc_y) - 1))
        pixel_x = max(0, min(pixel_x, TILE_SIZE - 1))
        pixel_y = max(0, min(pixel_y, TILE_SIZE - 1))

        return tile_x, tile_y, pixel_x, pixel_y

    def block_to_tile_pixel(self, bx: int, bz: int, zoom: int) -> tuple[int, int, int, int]:
        """Convert block coordinates to tile + pixel coordinates."""
        lat, lon = self.block_to_geo(bx, bz)
        return self.geo_to_tile_pixel(lat, lon, zoom)
