#!/usr/bin/env python3
"""CLI entry point for earth2mt - Earth terrain to Luanti world generator."""

import argparse
import hashlib
import os
import shutil
import sys
import time


def _spiral_offsets(max_radius: int):
    """Yield (x, z) offsets from the center in expanding square rings."""
    yield 0, 0
    for radius in range(1, max_radius + 1):
        for x in range(-radius, radius + 1):
            yield x, -radius
        for z in range(-radius + 1, radius + 1):
            yield radius, z
        for x in range(radius - 1, -radius - 1, -1):
            yield x, radius
        for z in range(radius - 1, -radius, -1):
            yield -radius, z


def find_spawn_position(
    radius_blocks: int,
    coords,
    elevation_src,
    landcover_src,
    climate_src,
) -> tuple[int, int, int]:
    """Pick a grounded spawn near the world center.

    We prefer the center if it is above sea level and not classified as water.
    If not, search outward in a spiral until we find the nearest solid surface.
    """
    from earth2mt.config import SEA_LEVEL, Biome
    from earth2mt.terrain.biome import classify_biome

    water_biomes = {
        Biome.VOID,
        Biome.DEEP_OCEAN,
        Biome.OCEAN,
        Biome.RIVER,
        Biome.FROZEN_RIVER,
    }

    search_radius = min(radius_blocks, 256)
    fallback = None

    for bx, bz in _spiral_offsets(search_radius):
        lat, lon = coords.block_to_geo(bx, bz)
        elevation = elevation_src.sample(coords, bx, bz)
        cover = landcover_src.sample(coords, bx, bz)
        mean_temp, min_temp, rainfall = climate_src.sample(lat, lon)
        biome = classify_biome(elevation, cover, mean_temp, min_temp, rainfall)
        terrain_y = int(round(elevation)) + SEA_LEVEL

        spawn_y = terrain_y + 1
        if fallback is None or spawn_y > fallback[1]:
            fallback = (bx, spawn_y, bz)

        if terrain_y >= SEA_LEVEL and biome not in water_biomes:
            return bx, spawn_y, bz

    if fallback is not None:
        return fallback

    return 0, SEA_LEVEL + 1, 0


def compute_world_seed(lat: float, lon: float, radius_km: float, scale: float) -> int:
    """Build a stable positive 63-bit seed from the generation parameters."""
    seed_input = f"{lat:.12f}:{lon:.12f}:{radius_km:.6f}:{scale:.6f}"
    digest = hashlib.blake2b(seed_input.encode("ascii"), digest_size=8).digest()
    seed = int.from_bytes(digest, "big") & ((1 << 63) - 1)
    return seed or 1


def _luanti_world_dirs() -> list[str]:
    """Return known Luanti world directories for common desktop installs."""
    return [
        os.path.expanduser("~/.var/app/org.luanti.luanti/.minetest/worlds"),
        os.path.expanduser("~/.minetest/worlds"),
        os.path.expanduser("~/.luanti/worlds"),
    ]


def _sanitize_world_basename(path: str) -> str:
    """Build a filesystem-safe label from an output path."""
    base = os.path.basename(os.path.normpath(path)) or "world"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in base)
    return safe.strip("._") or "world"


def find_luanti_launch_world(output_path: str) -> str | None:
    """Return a Luanti-managed launch path when the output is elsewhere.

    Flatpak Luanti only respected the singlenode world metadata when the world
    lived under its managed `worlds/` directory, so we mirror generated worlds
    there for launching when needed.
    """
    output_abs = os.path.abspath(output_path)
    output_real = os.path.realpath(output_abs)

    for worlds_dir in _luanti_world_dirs():
        if not os.path.isdir(worlds_dir):
            continue

        worlds_abs = os.path.abspath(worlds_dir)
        worlds_real = os.path.realpath(worlds_abs)
        try:
            if os.path.commonpath([output_real, worlds_real]) == worlds_real:
                return None
        except ValueError:
            pass

        label = _sanitize_world_basename(output_abs)
        suffix = hashlib.blake2b(output_abs.encode("utf-8"), digest_size=3).hexdigest()
        return os.path.join(worlds_abs, f"earth2mt_{label}_{suffix}")

    return None


def sync_luanti_launch_world(source_path: str, launch_path: str):
    """Copy the generated world into Luanti's managed worlds directory."""
    if os.path.isdir(launch_path):
        shutil.rmtree(launch_path)

    os.makedirs(launch_path, exist_ok=True)

    for filename in ("world.mt", "map_meta.txt", "map.sqlite"):
        src = os.path.join(source_path, filename)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(launch_path, filename))

    worldmods_src = os.path.join(source_path, "worldmods")
    if os.path.isdir(worldmods_src):
        shutil.copytree(worldmods_src, os.path.join(launch_path, "worldmods"), dirs_exist_ok=True)


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


def reset_output_world(path: str):
    """Remove generated world state that would interfere with regeneration."""
    files_to_remove = (
        "map.sqlite",
        "map.sqlite-shm",
        "map.sqlite-wal",
        "players.sqlite",
        "players.sqlite-journal",
        "auth.sqlite",
        "auth.sqlite-journal",
        "mod_storage.sqlite",
        "mod_storage.sqlite-journal",
        "env_meta.txt",
        "map_meta.txt",
        "force_loaded.txt",
        "ipban.txt",
    )

    for relpath in files_to_remove:
        target = os.path.join(path, relpath)
        if os.path.exists(target):
            os.remove(target)

    earth2mt_mod = os.path.join(path, "worldmods", "__earth2mt")
    if os.path.isdir(earth2mt_mod):
        shutil.rmtree(earth2mt_mod)


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
        resp = input("Warning: generated world data already exists at output path. Overwrite? [y/N] ")
        if resp.lower() != "y":
            print("Aborted.")
            sys.exit(0)
        reset_output_world(args.output)

    from earth2mt.terrain.coords import CoordinateTransform
    from earth2mt.data.elevation import ElevationSource
    from earth2mt.data.landcover import LandcoverSource
    from earth2mt.data.climate import ClimateSource
    from earth2mt.terrain.surface import generate_mapblock_column
    from earth2mt.world.world_setup import create_world
    from earth2mt.world.world_db import WorldDB
    from earth2mt.world.mapblock import serialize_mapblock
    from earth2mt.config import MAP_BLOCK_SIZE

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

    spawn_x, spawn_y, spawn_z = find_spawn_position(
        radius_blocks,
        coords,
        elevation_src,
        landcover_src,
        climate_src,
    )
    world_seed = compute_world_seed(lat, lon, args.radius, args.scale)
    world_name = _sanitize_world_basename(args.output)
    launch_world = find_luanti_launch_world(args.output)
    print(f"Spawn: ({spawn_x}, {spawn_y}, {spawn_z})")
    print(f"Seed: {world_seed}")
    if launch_world is not None:
        print(f"Luanti launch world: {launch_world}")

    # Create world
    create_world(args.output, (spawn_x, spawn_y, spawn_z), world_seed, world_name)
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

    if launch_world is not None:
        sync_luanti_launch_world(args.output, launch_world)

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.1f}s. World saved to: {args.output}")
    if launch_world is not None:
        print(f"Open this world in Luanti: {launch_world}")


if __name__ == "__main__":
    main()
