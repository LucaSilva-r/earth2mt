"""Create the Luanti world directory structure for Mineclonia."""

import os


def _write_map_meta(path: str, seed: int):
    """Write the minimum map metadata needed to force singlenode worlds."""
    with open(os.path.join(path, "map_meta.txt"), "w") as f:
        f.write(f"seed = {seed}\n")
        f.write("mg_name = singlenode\n")
        f.write("water_level = 1\n")
        f.write("mcl_singlenode_mapgen = false\n")
        f.write("[end_of_params]\n")


def create_world(
    path: str,
    spawn_pos: tuple[int, int, int] | None = None,
    seed: int | None = None,
    world_name: str | None = None,
):
    """Create the world directory with earth2mt-specific Mineclonia overrides."""
    os.makedirs(path, exist_ok=True)

    # world.mt
    with open(os.path.join(path, "world.mt"), "w") as f:
        f.write("backend = sqlite3\n")
        f.write("player_backend = sqlite3\n")
        f.write("auth_backend = sqlite3\n")
        f.write("mod_storage_backend = sqlite3\n")
        f.write("gameid = mineclonia\n")
        if world_name:
            f.write(f"world_name = {world_name}\n")
        if spawn_pos is not None:
            x, y, z = spawn_pos
            f.write(f"static_spawnpoint = ({x},{y},{z})\n")
            f.write("mcl_spawn_radius = 0\n")

    _write_map_meta(path, 1 if seed is None else seed)

    # Worldmod with world-specific Mineclonia overrides.
    mod_dir = os.path.join(path, "worldmods", "__earth2mt")
    os.makedirs(mod_dir, exist_ok=True)

    with open(os.path.join(mod_dir, "mod.conf"), "w") as f:
        f.write("name = __earth2mt\n")
        f.write("description = earth2mt world overrides for Mineclonia\n")
        f.write("optional_depends = mcl_spawn, mcl_biome_dispatch, mcl_mapgen_core, mcl_biomes\n")

    with open(os.path.join(mod_dir, "mcl_levelgen.conf"), "w") as f:
        f.write("disable_mcl_levelgen = true\n")

    with open(os.path.join(mod_dir, "init.lua"), "w") as f:
        f.write("-- earth2mt world overrides: keep Mineclonia from regenerating terrain.\n")
        f.write("local earth2mt_disabled_generators = {\n")
        f.write('\t"world_structure",\n')
        f.write('\t"end_fixes",\n')
        f.write('\t"set_param2_nodes",\n')
        f.write('\t"structures",\n')
        f.write('\t"villages",\n')
        f.write('\t"end_island",\n')
        f.write('\t"railcorridors",\n')
        f.write('\t"dungeons",\n')
        f.write('\t"chorus_grow",\n')
        f.write("}\n")
        f.write("\n")
        f.write("local function earth2mt_noop(...)\n")
        f.write("\treturn nil\n")
        f.write("end\n")
        f.write("\n")
        f.write("minetest.register_on_mods_loaded(function()\n")
        f.write('\tminetest.log("action", "[__earth2mt] Locking world to pre-generated terrain")\n')
        f.write("\tif mcl_mapgen_core and mcl_mapgen_core.unregister_generator then\n")
        f.write("\t\tfor _, id in ipairs(earth2mt_disabled_generators) do\n")
        f.write("\t\t\tmcl_mapgen_core.unregister_generator(id)\n")
        f.write("\t\tend\n")
        f.write("\tend\n")
        f.write("\tif minetest.clear_registered_biomes then\n")
        f.write("\t\tminetest.clear_registered_biomes()\n")
        f.write("\tend\n")
        f.write("\tif minetest.clear_registered_decorations then\n")
        f.write("\t\tminetest.clear_registered_decorations()\n")
        f.write("\tend\n")
        f.write("\tif minetest.clear_registered_schematics then\n")
        f.write("\t\tminetest.clear_registered_schematics()\n")
        f.write("\tend\n")
        f.write("\tif minetest.clear_registered_ores then\n")
        f.write("\t\tminetest.clear_registered_ores()\n")
        f.write("\tend\n")
        f.write("\tif minetest.generate_decorations then\n")
        f.write("\t\tminetest.generate_decorations = earth2mt_noop\n")
        f.write("\tend\n")
        f.write("\tif minetest.generate_ores then\n")
        f.write("\t\tminetest.generate_ores = earth2mt_noop\n")
        f.write("\tend\n")
        f.write("end)\n")
        f.write("\n")
        if spawn_pos is not None:
            x, y, z = spawn_pos
            spawn_y = y - 0.5
            f.write(f"local earth2mt_spawn = vector.new({x}, {spawn_y}, {z})\n")
            f.write("\n")
            f.write("local function earth2mt_spawn_pos()\n")
            f.write("\treturn vector.new(earth2mt_spawn.x, earth2mt_spawn.y, earth2mt_spawn.z)\n")
            f.write("end\n")
            f.write("\n")
            f.write("local function earth2mt_place_player(player)\n")
            f.write("\tif not player or not player:is_player() then\n")
            f.write("\t\treturn\n")
            f.write("\tend\n")
            f.write("\tlocal pos = earth2mt_spawn_pos()\n")
            f.write("\tminetest.load_area(vector.offset(pos, -1, -1, -1), vector.offset(pos, 1, 2, 1))\n")
            f.write("\tplayer:set_pos(pos)\n")
            f.write("end\n")
            f.write("\n")
            f.write("if mcl_biome_dispatch then\n")
            f.write("\tmcl_biome_dispatch.get_spawn_point_2d = earth2mt_spawn_pos\n")
            f.write("\tmcl_biome_dispatch.next_respawn_position = function(_)\n")
            f.write("\t\treturn earth2mt_spawn_pos()\n")
            f.write("\tend\n")
            f.write("end\n")
            f.write("\n")
            f.write("if mcl_spawn then\n")
            f.write("\tlocal original_spawn = mcl_spawn.spawn\n")
            f.write("\tmcl_spawn.get_world_spawn_pos = function(_)\n")
            f.write("\t\treturn earth2mt_spawn_pos(), false\n")
            f.write("\tend\n")
            f.write("\tmcl_spawn.spawn = function(player)\n")
            f.write("\t\tif player:get_meta():get_string(\"mcl_beds:spawn\") ~= \"\" then\n")
            f.write("\t\t\treturn original_spawn(player)\n")
            f.write("\t\tend\n")
            f.write("\t\tearth2mt_place_player(player)\n")
            f.write("\t\treturn true\n")
            f.write("\tend\n")
            f.write("else\n")
            f.write("\tminetest.register_on_newplayer(earth2mt_place_player)\n")
            f.write("\tminetest.register_on_respawnplayer(function(player)\n")
            f.write("\t\tearth2mt_place_player(player)\n")
            f.write("\t\treturn true\n")
            f.write("\tend)\n")
            f.write("end\n")
