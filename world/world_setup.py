"""Create the Luanti world directory structure for Mineclonia."""

import os


def create_world(path: str):
    """Create the world directory with world.mt and singlenode mapgen worldmod."""
    os.makedirs(path, exist_ok=True)

    # world.mt
    with open(os.path.join(path, "world.mt"), "w") as f:
        f.write("backend = sqlite3\n")
        f.write("player_backend = sqlite3\n")
        f.write("auth_backend = sqlite3\n")
        f.write("mod_storage_backend = sqlite3\n")
        f.write("gameid = mineclonia\n")

    # Worldmod to force singlenode mapgen
    mod_dir = os.path.join(path, "worldmods", "__earth2mt")
    os.makedirs(mod_dir, exist_ok=True)

    with open(os.path.join(mod_dir, "init.lua"), "w") as f:
        f.write('minetest.set_mapgen_params({chunksize = 1})\n')
        f.write('minetest.set_mapgen_params({mgname = "singlenode"})\n')
