import unittest
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = ROOT.parent
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from earth2mt.config import (
    BROWN_TERRACOTTA,
    Cover,
    DIRT,
    GRASS_BLOCK,
    GRAVEL,
    Landform,
    LIGHT_GRAY_TERRACOTTA,
    ORANGE_TERRACOTTA,
    PODZOL,
    RED_TERRACOTTA,
    SAND,
    SoilSuborder,
    TERRACOTTA,
    WHITE_TERRACOTTA,
    YELLOW_TERRACOTTA,
)
from earth2mt.terrain.soil import (
    GrowthPredictors,
    compute_slope,
    sample_soil_profile,
    select_soil_texture,
)


class SoilSelectionTests(unittest.TestCase):
    def test_sea_uses_gravel_ocean_floor(self):
        predictors = GrowthPredictors(
            annual_rainfall=800.0,
            organic_carbon_content=30,
            slope=0,
            cover=Cover.WATER,
            soil_suborder=SoilSuborder.OCEAN,
            landform=Landform.SEA,
        )

        profile = sample_soil_profile(select_soil_texture(predictors), 1, 0, 0, 0, 0)
        self.assertTrue(profile)
        self.assertTrue(all(block == GRAVEL for block in profile))

    def test_grassy_soil_keeps_grass_surface_and_dirt_below(self):
        predictors = GrowthPredictors(
            annual_rainfall=900.0,
            organic_carbon_content=50,
            slope=0,
            cover=Cover.GRASSLAND,
            soil_suborder=SoilSuborder.UDALFS,
            landform=Landform.LAND,
        )

        profile = sample_soil_profile(select_soil_texture(predictors), 7, 123, 72, 456, 0)
        self.assertEqual(profile[0], GRASS_BLOCK)
        for block in profile[1:]:
            self.assertEqual(block, DIRT)

    def test_barren_sandy_land_uses_desert_sand(self):
        predictors = GrowthPredictors(
            annual_rainfall=100.0,
            organic_carbon_content=0,
            slope=0,
            cover=Cover.BARE_UNCONSOLIDATED,
            soil_suborder=SoilSuborder.PSAMMENTS,
            landform=Landform.LAND,
        )

        profile = sample_soil_profile(select_soil_texture(predictors), 11, 20, 80, 30, 0)
        self.assertTrue(profile)
        self.assertTrue(all(block == SAND for block in profile))

    def test_consolidated_sand_turns_into_mesa_terracotta(self):
        predictors = GrowthPredictors(
            annual_rainfall=100.0,
            organic_carbon_content=0,
            slope=20,
            cover=Cover.BARE_CONSOLIDATED,
            soil_suborder=SoilSuborder.PSAMMENTS,
            landform=Landform.LAND,
        )

        allowed_blocks = {
            TERRACOTTA,
            ORANGE_TERRACOTTA,
            YELLOW_TERRACOTTA,
            BROWN_TERRACOTTA,
            RED_TERRACOTTA,
            WHITE_TERRACOTTA,
            LIGHT_GRAY_TERRACOTTA,
        }

        profile = sample_soil_profile(select_soil_texture(predictors), 19, 200, 96, 40, 20)
        self.assertTrue(profile)
        self.assertTrue(all(block in allowed_blocks for block in profile))

    def test_spodosol_grass_adds_podzol_mix(self):
        predictors = GrowthPredictors(
            annual_rainfall=1100.0,
            organic_carbon_content=50,
            slope=0,
            cover=Cover.BROADLEAF_DECIDUOUS,
            soil_suborder=SoilSuborder.ORTHODS,
            landform=Landform.LAND,
        )

        profile = sample_soil_profile(select_soil_texture(predictors), 23, 64, 70, 18, 0)
        self.assertIn(profile[0], {GRASS_BLOCK, PODZOL})
        for block in profile[1:]:
            self.assertEqual(block, DIRT)

    def test_compute_slope_uses_steepest_diagonal(self):
        elevations = np.array([
            [90.0, 100.0, 100.0],
            [100.0, 100.0, 100.0],
            [100.0, 100.0, 100.0],
        ], dtype=np.float32)

        slope = compute_slope(elevations, 1, 1, 0.1)
        self.assertEqual(slope, 45)


if __name__ == "__main__":
    unittest.main()
