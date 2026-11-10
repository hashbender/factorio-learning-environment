"""Blueprints, ghosts, deconstruction and the construction section (no server; Lua via lupa).

The fake blueprint and ghost positions are the ones Factorio 2.0.73 gave live: a blueprint of an
assembling-machine-1 at (20.5, 20.5), an inserter facing east at (22.5, 20.5) and a wooden chest at
(23.5, 20.5), placed at (40, 20), puts them at (39.5, 20.5), (41.5, 20.5), (42.5, 20.5); turned
east at (40, 40), at (40.5, 39.5), (40.5, 41.5), (40.5, 42.5).
"""

import json
from pathlib import Path

import pytest

from fle.env.entities import BoundingBox, Position
from fle.env.gym_env.observation import Observation
from fle.env.gym_env.observation_formatter import TreeObservationFormatter
from fle.env.tools.construction import area_args, decode, entity_args

ROOT = Path(__file__).resolve().parents[2] / "fle/env"
NEW_LUA = [
    "mods/utils.lua",
    "tools/agent/create_blueprint/server.lua",
    "tools/agent/list_blueprints/server.lua",
    "tools/agent/get_blueprint/server.lua",
    "tools/agent/delete_blueprint/server.lua",
    "tools/agent/place_blueprint/server.lua",
    "tools/agent/mark_for_deconstruction/server.lua",
    "tools/agent/cancel_deconstruction/server.lua",
    "tools/agent/get_construction_status/server.lua",
    "tools/agent/place_entity/server.lua",
]

STUB = """
defines = {events = {on_tick = 0}, direction = {north = 0, east = 4, south = 8, west = 12},
           build_mode = {normal = 0, forced = 1}, entity_status = {no_power = 54, low_power = 14}}
script = {on_event = function() end}
storage = {actions = {}, utils = {}}
local sizes = {["assembling-machine-1"] = 3, inserter = 1, ["wooden-chest"] = 1}
prototypes = {entity = {}}
for name, n in pairs(sizes) do
    prototypes.entity[name] = {tile_width = n, tile_height = n, items_to_place_this = {{name = name, count = 1}}}
end
charted = true
found = {}       -- what find_entities_filtered returns
built = {}       -- the ghosts build_blueprint returns
force = {name = "player", is_chunk_charted = function() return charted end, logistic_networks = {}}
nets = {}
surface = {name = "nauvis",
    find_entities_filtered = function(f) return found end,
    is_chunk_generated = function() return charted end,
    get_tile = function() return {valid = true, name = "grass-1", collides_with = function() return false end} end,
    find_logistic_networks_by_construction_area = function() return nets end}
character = {surface = surface, force = force, position = {x = 0, y = 0}}
storage.utils.ensure_valid_character = function() return character end
local bp_entities = {
    {entity_number = 1, name = "assembling-machine-1", position = {x = 20.5, y = 20.5}, recipe = "iron-gear-wheel"},
    {entity_number = 2, name = "wooden-chest", position = {x = 23.5, y = 20.5}},
    {entity_number = 3, name = "inserter", position = {x = 22.5, y = 20.5}, direction = 4},
}
stack = {valid_for_read = true, is_blueprint = true,
    get_blueprint_entities = function() return bp_entities end,
    build_blueprint = function(args) last_build = args return built end}
local inv = {stack}
inv.valid = true
game = {create_inventory = function() return inv end}
"""


def _to_py(v):
    if hasattr(v, "items"):
        d = dict(v.items())
        if (
            d
            and all(isinstance(k, int) for k in d)
            and sorted(d) == list(range(1, len(d) + 1))
        ):
            return [_to_py(d[k]) for k in sorted(d)]
        return {str(k): _to_py(x) for k, x in d.items()}
    return v


def _lupa():
    # Factorio runs Lua 5.2 (lupa's default 5.5 makes loop variables constant)
    return pytest.importorskip("lupa.lua52")


@pytest.fixture()
def lua():
    rt = _lupa().LuaRuntime(unpack_returned_tuples=True)
    rt.execute(STUB)
    rt.execute("helpers = {}")
    rt.globals().helpers.table_to_json = lambda t: json.dumps(_to_py(t))
    for rel in ("mods/utils.lua", "tools/agent/place_blueprint/server.lua"):
        rt.execute((ROOT / rel).read_text())
    rt.execute("storage.utils.ensure_valid_character = function() return character end")
    rt.execute(
        "storage.fmg_blueprints = {inventory = game.create_inventory(), names = {gears = 1}, "
        "placements = {}, next_placement = 1, scratch = game.create_inventory()}"
    )
    return rt


def _ghosts(lua, positions):
    lua.execute("built = {}")
    for name, x, y in positions:
        lua.execute(
            f"table.insert(built, {{valid = true, ghost_name = '{name}', position = {{x = {x}, y = {y}}}}})"
        )


def _place(lua, x, y, direction=0):
    out = lua.eval(
        f"storage.actions.place_blueprint(1, 'gears', {x}, {y}, {direction}, false)"
    )
    return json.loads(bytes.fromhex(out.strip('"')).decode())


def test_new_lua_compiles():
    lupa = _lupa()
    for rel in NEW_LUA:
        lupa.LuaRuntime().compile((ROOT / rel).read_text())


def test_place_all_ghosts(lua):
    _ghosts(
        lua,
        [
            ("assembling-machine-1", 39.5, 20.5),
            ("inserter", 41.5, 20.5),
            ("wooden-chest", 42.5, 20.5),
        ],
    )
    r = _place(lua, 40, 20)
    assert r["ghosts_placed"] == 3 and r["refused_count"] == 0
    assert r["items_needed"] == {
        "assembling-machine-1": 1,
        "inserter": 1,
        "wooden-chest": 1,
    }
    assert (
        lua.eval("last_build.build_mode") == 0
        and lua.eval("last_build.skip_fog_of_war") is False
    )
    assert lua.eval("#storage.fmg_blueprints.placements") == 1


def test_refused_part_is_reported_with_what_is_in_the_way(lua):
    _ghosts(lua, [("assembling-machine-1", 39.5, 20.5), ("inserter", 41.5, 20.5)])
    lua.execute(
        "found = {{valid = true, type = 'tree', name = 'tree-01', position = {x = 42.5, y = 20.5}}}"
    )
    r = _place(lua, 40, 20)
    assert r["ghosts_placed"] == 2 and r["refused_count"] == 1
    assert r["refused"] == [
        {
            "name": "wooden-chest",
            "x": 42.5,
            "y": 20.5,
            "reason": "blocked by tree-01 at (42.5, 20.5)",
        }
    ]


def test_turned_east_positions_match_the_game(lua):
    lua.execute(
        "found = {{valid = true, type = 'simple-entity', name = 'rock', position = {x = 0, y = 0}}}"
    )
    _ghosts(lua, [])
    r = _place(lua, 40, 40, 4)
    got = sorted((e["name"], e["x"], e["y"]) for e in r["refused"])
    assert got == [
        ("assembling-machine-1", 40.5, 39.5),
        ("inserter", 40.5, 41.5),
        ("wooden-chest", 40.5, 42.5),
    ]
    assert (
        r["ghosts_placed"] == 0 and lua.eval("#storage.fmg_blueprints.placements") == 0
    )


def test_prediction_follows_the_game_if_it_snaps_differently(lua):
    # the game put everything one tile further right than predicted: the report follows it
    _ghosts(
        lua,
        [
            ("assembling-machine-1", 40.5, 20.5),
            ("inserter", 42.5, 20.5),
            ("wooden-chest", 43.5, 20.5),
        ],
    )
    r = _place(lua, 40, 20)
    assert r["ghosts_placed"] == 3 and r["refused_count"] == 0


def test_uncharted_is_refused(lua):
    lua.execute("charted = false")
    with pytest.raises(Exception, match="not been generated or charted"):
        _place(lua, 40, 20)
    assert lua.eval("last_build") is None


def test_robot_blocker_reasons(lua):
    ghost = "{position = {x = 1, y = 1}, surface = surface}"
    blocker = lua.eval(
        f"function(item) return storage.utils.robot_blocker({ghost}, force, item) end"
    )
    assert blocker("inserter") == "not in the construction area of any roboport"
    lua.execute(
        "nets = {{all_construction_robots = 0, get_item_count = function() return 5 end}}"
    )
    assert blocker("inserter") == "no construction robots in the roboport network"
    lua.execute(
        "nets = {{all_construction_robots = 3, get_item_count = function() return 0 end}}"
    )
    assert blocker("inserter") == "no inserter in the roboport network's storage"
    assert blocker(None) is None
    lua.execute(
        "nets = {{all_construction_robots = 3, get_item_count = function() return 1 end}}"
    )
    assert blocker("inserter") is None


def test_args_and_decode():
    bb = BoundingBox(
        left_top=Position(x=1, y=2),
        right_bottom=Position(x=5, y=6),
        left_bottom=Position(x=1, y=6),
        right_top=Position(x=5, y=2),
    )
    assert area_args(bb) == (1.0, 2.0, 5.0, 6.0)
    assert area_args((Position(x=1, y=2), Position(x=3, y=4))) == (1.0, 2.0, 3.0, 4.0)
    with pytest.raises(ValueError):
        area_args("nope")

    class E:
        name, position = "inserter", Position(x=1.5, y=2.5)

    assert entity_args([E()]) == [{"name": "inserter", "x": 1.5, "y": 2.5}]
    assert entity_args([]) is None
    hexed = json.dumps({"blueprints": {}, "refused": {}, "entities": {}}).encode().hex()
    assert decode(hexed, "x", str) == {"blueprints": [], "refused": [], "entities": {}}
    with pytest.raises(
        Exception, match="Could not place blueprint - No blueprint named a"
    ):
        decode("No blueprint named a", "place blueprint", str)


STATUS = {
    "networks": [
        {
            "id": 2,
            "roboports": 1,
            "roboports_no_power": 0,
            "roboports_low_power": 1,
            "construction_robots": 10,
            "construction_robots_idle": 7,
            "logistic_robots": 0,
            "logistic_robots_idle": 0,
            "storage": {"iron-plate": 50, "inserter": 3},
            "storage_item_types": 3,
        }
    ],
    "ghosts": 6,
    "ghosts_waiting": [
        {
            "reason": "no iron-gear-wheel in the roboport network's storage",
            "count": 2,
            "x": 40.5,
            "y": 20.5,
        }
    ],
    "deconstruction": 0,
    "deconstruction_waiting": [],
    "placements": [
        {
            "id": 1,
            "blueprint": "gears",
            "x": 40.5,
            "y": 20.5,
            "ghosts_placed": 3,
            "built": 1,
            "ghosts_waiting": 2,
        }
    ],
}


def test_construction_section():
    text = TreeObservationFormatter.format_construction(STATUS)
    assert text.splitlines() == [
        "### Construction",
        "- roboport network 2: 1 roboports (0 without power, 1 low power), construction robots 10 (7 idle), "
        "logistic robots 0 (0 idle), storage: iron-plate 50, inserter 3 (+1 more item types)",
        "- ghosts: 6; not being built: 2 no iron-gear-wheel in the roboport network's storage (first at (40.5, 20.5))",
        "- marked for deconstruction: 0",
        "- placement 1 (blueprint gears at (40.5, 20.5)): 3 ghosts placed, 1 built, 2 still ghosts",
    ]
    assert TreeObservationFormatter.format_construction(None) == ""


def test_construction_round_trip_and_absent_by_default():
    obs = Observation.from_dict({"construction": STATUS})
    assert obs.construction == STATUS
    assert obs.to_dict()["construction"] == STATUS
    assert "construction" not in Observation.from_dict({}).to_dict()
    raw = (
        TreeObservationFormatter(include_research=False)
        .format(Observation.from_dict({}))
        .raw_str
    )
    assert "### Construction" not in raw
