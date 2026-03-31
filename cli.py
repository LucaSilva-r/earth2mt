#!/usr/bin/env python3
"""CLI entry point for earth2mt - Earth terrain to Luanti world generator."""

import argparse
import os
import sys
import time


def parse_args():
    parser = argparse.ArgumentParser(
        prog="earth2mt",
        description="Generate Luanti (Mineclonia) worlds from real-world terrain data.",
    )

    location = parser.add_mutually_exclusive_group(required=True)
    location.add_argument(
        "--coords",
        nargs=2,
        type=float,
        metavar=("LAT", "LON"),
        help="Center coordinates (latitude, longitude)",
    )
    location.add_argument(
        "--place",
        type=str,
        help="Place name to geocode (e.g. 'Rome, Italy')",
    )

    parser.add_argument(
        "--radius",
        type=float,
        default=5.0,
        help="Radius in km (default: 5.0)",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Meters per block (default: 1.0)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        required=True,
        help="Output world directory path",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=os.path.expanduser("~/.cache/earth2mt"),
        help="Tile cache directory (default: ~/.cache/earth2mt/)",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # Resolve center coordinates
    if args.place:
        from earth2mt.data.geocoder import geocode
        print(f"Geocoding '{args.place}'...")
        result = geocode(args.place)
        if result is None:
            print(f"Error: Could not geocode '{args.place}'", file=sys.stderr)
            sys.exit(1)
        lat, lon = result
        print(f"  -> {lat:.4f}, {lon:.4f}")
    else:
        lat, lon = args.coords

    print(f"Center: {lat:.4f}, {lon:.4f}")
    print(f"Radius: {args.radius} km")
    print(f"Scale: {args.scale} m/block")
    print(f"Output: {args.output}")

    # Check output path
    if os.path.exists(os.path.join(args.output, "map.sqlite")):
        resp = input("Warning: map.sqlite already exists at output path. Overwrite? [y/N] ")
        if resp.lower() != "y":
            print("Aborted.")
            sys.exit(0)
        os.remove(os.path.join(args.output, "map.sqlite"))

    from earth2mt.terrain.coords import CoordinateTransform
    from earth2mt.data.elevation import ElevationSource
    from earth2mt.data.landcover import LandcoverSource
    from earth2mt.data.climate import ClimateSource
    from earth2mt.terrain.biome import classify_biome
    from earth2mt.terrain.soil import select_surface_blocks
    from earth2mt.terrain.surface import generate_mapblock_column
    from earth2mt.world.world_setup import create_world
    from earth2mt.world.world_db import WorldDB
    from earth2mt.world.mapblock import serialize_mapblock
    from earth2mt.config import MAP_BLOCK_SIZE, SEA_LEVEL, WORLD_FLOOR

    # Set up coordinate transform
    coords = CoordinateTransform(lat, lon, args.scale)

    # Calculate block bounds
    radius_blocks = int((args.radius * 1000) / args.scale)
    min_bx = -radius_blocks
    max_bx = radius_blocks
    min_bz = -radius_blocks
    max_bz = radius_blocks

    # MapBlock range
    mb_min_x = min_bx // MAP_BLOCK_SIZE
    mb_max_x = max_bx // MAP_BLOCK_SIZE
    mb_min_z = min_bz // MAP_BLOCK_SIZE
    mb_max_z = max_bz // MAP_BLOCK_SIZE

    total_columns = (mb_max_x - mb_min_x + 1) * (mb_max_z - mb_min_z + 1)
    print(f"Generating {total_columns} MapBlock columns "
          f"({mb_max_x - mb_min_x + 1} x {mb_max_z - mb_min_z + 1})...")

    # Initialize data sources
    elevation_src = ElevationSource(args.cache_dir, args.scale)
    landcover_src = LandcoverSource(args.cache_dir, args.scale)
    climate_src = ClimateSource(args.cache_dir)

    # Create world
    create_world(args.output)
    db = WorldDB(args.output)

    start_time = time.time()
    done = 0

    try:
        db.begin()
        batch_count = 0

        for mb_x in range(mb_min_x, mb_max_x + 1):
            for mb_z in range(mb_min_z, mb_max_z + 1):
                # Generate all MapBlocks for this column
                mapblocks = generate_mapblock_column(
                    mb_x, mb_z, coords,
                    elevation_src, landcover_src, climate_src,
                )

                for mb_y, block_data in mapblocks:
                    data = serialize_mapblock(block_data, mb_x, mb_y, mb_z)
                    db.save_block(mb_x, mb_y, mb_z, data)
                    batch_count += 1

                    if batch_count >= 1000:
                        db.end()
                        db.begin()
                        batch_count = 0

                done += 1
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                remaining = (total_columns - done) / rate if rate > 0 else 0
                print(f"\r  [{done}/{total_columns}] "
                      f"{done * 100 / total_columns:.1f}% "
                      f"({rate:.1f} col/s, ~{remaining:.0f}s remaining)   ",
                      end="", flush=True)

        db.end()
    finally:
        db.close()

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.1f}s. World saved to: {args.output}")


if __name__ == "__main__":
    main()
