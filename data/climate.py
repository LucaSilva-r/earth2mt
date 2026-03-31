"""WorldClim climate raster: mean temperature, min temperature, annual rainfall.

The data is a single XZ-compressed file (4320x2160 global grid) from the Terrarium server.
Format: XZ-compressed stream of 3 layers, each 4320*2160 bytes (uint8 packed):
  1. Mean temperature (packed)
  2. Min temperature (packed)
  3. Annual rainfall (packed)

Unpacking:
  Temperature: TEMP_MIN + TEMP_RANGE * (packed / 255) ^ TEMP_CURVE
  Rainfall: RAIN_MIN + RAIN_RANGE * (packed / 255) ^ RAIN_CURVE
"""

import lzma
import math
import os
import time
import urllib.request
from pathlib import Path

import numpy as np

CLIMATE_URL = "https://terrarium.gegy.dev/geo3/climatic_variables.xz"
CLIMATE_WIDTH = 4320
CLIMATE_HEIGHT = 2160
CLIMATE_PIXELS = CLIMATE_WIDTH * CLIMATE_HEIGHT

# Unpacking constants
TEMP_MIN = -40.0
TEMP_MAX = 45.0
TEMP_RANGE = TEMP_MAX - TEMP_MIN
TEMP_CURVE = 1.0

RAIN_MIN = 0.0
RAIN_RANGE = 7200.0
RAIN_CURVE = 2.3

# Defaults for out-of-bounds
STANDARD_TEMPERATURE = 14.0
STANDARD_RAINFALL = 600


def _unpack_temperature(packed: np.ndarray) -> np.ndarray:
    shifted = packed.astype(np.float32)
    return TEMP_MIN + TEMP_RANGE * np.power(shifted / 255.0, TEMP_CURVE)


def _unpack_rainfall(packed: np.ndarray) -> np.ndarray:
    shifted = packed.astype(np.float32)
    return RAIN_MIN + RAIN_RANGE * np.power(shifted / 255.0, RAIN_CURVE)


class ClimateSource:
    def __init__(self, cache_dir: str):
        self.cache_path = Path(cache_dir) / "climatic_variables.xz"
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        self.mean_temperature: np.ndarray | None = None
        self.min_temperature: np.ndarray | None = None
        self.annual_rainfall: np.ndarray | None = None

    def _ensure_loaded(self):
        if self.mean_temperature is not None:
            return

        raw = self._get_raw_data()
        decompressed = lzma.decompress(raw, format=lzma.FORMAT_XZ)

        expected = CLIMATE_PIXELS * 3
        if len(decompressed) < expected:
            raise ValueError(f"Climate data too short: {len(decompressed)} < {expected}")

        mean_packed = np.frombuffer(decompressed[0:CLIMATE_PIXELS], dtype=np.uint8)
        min_packed = np.frombuffer(decompressed[CLIMATE_PIXELS:CLIMATE_PIXELS * 2], dtype=np.uint8)
        rain_packed = np.frombuffer(decompressed[CLIMATE_PIXELS * 2:CLIMATE_PIXELS * 3], dtype=np.uint8)

        self.mean_temperature = _unpack_temperature(mean_packed).reshape((CLIMATE_HEIGHT, CLIMATE_WIDTH))
        self.min_temperature = _unpack_temperature(min_packed).reshape((CLIMATE_HEIGHT, CLIMATE_WIDTH))
        self.annual_rainfall = _unpack_rainfall(rain_packed).reshape((CLIMATE_HEIGHT, CLIMATE_WIDTH))

    def _get_raw_data(self) -> bytes:
        if self.cache_path.exists():
            return self.cache_path.read_bytes()

        print("Downloading climate data...")
        req = urllib.request.Request(CLIMATE_URL, headers={"User-Agent": "earth2mt"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        self.cache_path.write_bytes(data)
        print(f"  Climate data cached ({len(data)} bytes)")
        return data

    def sample(self, lat: float, lon: float) -> tuple[float, float, float]:
        """Get (mean_temp, min_temp, annual_rainfall) for a geographic coordinate.

        Climate raster: x=0 is lon=-180, x=4319 is lon=+180
                        y=0 is lat=+90, y=2159 is lat=-90
        """
        self._ensure_loaded()

        # Convert lat/lon to pixel coordinates
        px = int(((lon + 180.0) / 360.0) * CLIMATE_WIDTH)
        py = int(((90.0 - lat) / 180.0) * CLIMATE_HEIGHT)

        if px < 0 or px >= CLIMATE_WIDTH or py < 0 or py >= CLIMATE_HEIGHT:
            return STANDARD_TEMPERATURE, STANDARD_TEMPERATURE, STANDARD_RAINFALL

        return (
            float(self.mean_temperature[py, px]),
            float(self.min_temperature[py, px]),
            float(self.annual_rainfall[py, px]),
        )
