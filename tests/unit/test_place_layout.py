"""place_layout: check everything first, then build stop by stop from the inventory. Server-free.

The Lua action runs in lupa (Lua 5.2, as Factorio) against a stub surface; the client runs with
execute and move_to stubbed onto that same Lua state."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fle.env.entities import Direction, LayoutResult, Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.place_layout.client import PlaceLayout

ROOT = Path(__file__).resolve().parents[2] / "fle/env"
SERVER_LUA = ROOT / "tools/agent/place_layout/server.lua"

# A stub map: water on tiles x >= 40, a tree on tile (5, -3), ungenerated map at y >= 64.
# Recipes: iron-gear-wheel unlocked, electronic-circuit locked.
STUB_LUA = """
defines = {direction = {north = 0, east = 4, south = 8, west = 12}}
local function proto(type, w, h, extra)
    local p = {type = type, name = "", tile_width = w, tile_height = h,
               collision_box = {left_top = {x = -w / 2 + 0.1, y = -h / 2 + 0.1},
                                right_bottom = {x = w / 2 - 0.1, y = h / 2 - 0.1}},
               collision_mask = {layers = {object = true, water_tile = true, player = true}}}
    for k, v in pairs(extra or {}) do p[k] = v end
    return p
end
prototypes = {
    entity = {
        ["stone-furnace"] = proto("furnace", 2, 2),
        ["burner-inserter"] = proto("inserter", 1, 1, {filter_count = 0}),
        ["fast-inserter"] = proto("inserter", 1, 1, {filter_count = 5}),
        ["transport-belt"] = proto("transport-belt", 1, 1),
        ["underground-belt"] = proto("underground-belt", 1, 1),
        ["small-electric-pole"] = proto("electric-pole", 1, 1),
        ["assembling-machine-1"] = proto("assembling-machine", 3, 3, {crafting_categories = {crafting = true}}),
        ["steam-engine"] = proto("generator", 3, 5),
        ["tree-01"] = proto("tree", 1, 1),
    },
    item = {["iron-plate"] = {}, ["coal"] = {}},
}
for name, p in pairs(prototypes.entity) do
    p.name = name
    if name ~= "tree-01" then prototypes.item[name] = {place_result = p} end
end
recipes = {["iron-gear-wheel"] = {enabled = true, category = "crafting"},
           ["electronic-circuit"] = {enabled = false, category = "crafting"}}
game = {tick = 1000}
world = {}
local function new_entity(name, x, y, dir, extra)
    local p = prototypes.entity[name]
    local e = {valid = true, name = name, type = p.type, prototype = p, position = {x = x, y = y},
               direction = dir or 0, supports_direction = p.type ~= "furnace" and p.type ~= "electric-pole"}
    for k, v in pairs(extra or {}) do e[k] = v end
    e.get_recipe = function() return e.recipe and {name = e.recipe} or nil end
    e.set_recipe = function(r) e.recipe = r; return {} end
    e.set_filter = function(i, f) e.filter = f end
    if e.type == "assembling-machine" then e.direction = 0 end
    table.insert(world, e)
    return e
end
new_entity("tree-01", 5.5, -2.5)
local function box(e)
    local w, h = e.prototype.tile_width, e.prototype.tile_height
    if e.direction == 4 or e.direction == 12 then w, h = h, w end
    return e.position.x - w / 2, e.position.y - h / 2, e.position.x + w / 2, e.position.y + h / 2
end
local function water(tx) return tx >= 40 end
player = {valid = true, position = {x = 0.5, y = 0.5}, reach_distance = 10,
          inv = {["stone-furnace"] = 50, ["burner-inserter"] = 50, ["transport-belt"] = 100,
                   ["small-electric-pole"] = 20, ["assembling-machine-1"] = 5, ["fast-inserter"] = 5,
                   ["underground-belt"] = 4},
          force = {recipes = recipes,
                   is_chunk_charted = function(s, chunk) return false end}}
player.get_item_count = function(name) return player.inv[name] or 0 end
player.remove_item = function(stack) player.inv[stack.name] = player.inv[stack.name] - stack.count end
player.teleport = function(p) player.position = {x = p.x or p[1], y = p.y or p[2]} end
created = {}
local surface = {
    is_chunk_generated = function(chunk) return chunk.y < 2 end,
    find_entities_filtered = function(f)
        local out = {}
        for _, e in ipairs(world) do
            if e.valid then
                local ok = true
                if f.name and f.name ~= e.name then ok = false end
                if f.position then
                    ok = ok and math.abs(e.position.x - (f.position.x or f.position[1])) < 0.01
                         and math.abs(e.position.y - (f.position.y or f.position[2])) < 0.01
                end
                if f.area then
                    local l, t, r, b = box(e)
                    ok = ok and l < f.area[2][1] and r > f.area[1][1] and t < f.area[2][2] and b > f.area[1][2]
                end
                if ok then table.insert(out, e) end
            end
        end
        return out
    end,
    get_tile = function(tx, ty)
        local name = water(tx) and "water" or "grass-1"
        return {valid = true, name = name,
                collides_with = function(layer) return name == "water" end}
    end,
    create_entity = function(spec)
        local e = new_entity(spec.name, spec.position.x, spec.position.y, spec.direction,
                             {belt_to_ground_type = spec.type})
        table.insert(created, spec)
        return e
    end,
    find_non_colliding_position = function(name, p, r, step) return {x = p.x, y = p.y} end,
}
player.surface = surface
storage = {actions = {}, agent_characters = {player}, utils = {
    get_entity_direction = function(entity, direction) return direction end,
    ensure_valid_character = function() return player end,
    build_item = function(name) if prototypes.item[name] then return name, 1 end return nil, 0 end,
    revive_ghost = function() return nil end,
    hex_json = function(t)
        local s = helpers.table_to_json(t)
        return "\\"" .. (s:gsub(".", function(c) return string.format("%02x", c:byte()) end)) .. "\\""
    end,
    can_place_entity = function(p, name, position, direction)
        local pr = prototypes.entity[name]
        local w, h = pr.tile_width, pr.tile_height
        if direction == 4 or direction == 12 then w, h = h, w end
        local l, t = position.x - w / 2, position.y - h / 2
        local function overlaps(a, b, c, d) return a < l + w and c > l and b < t + h and d > t end
        local px, py = player.position.x, player.position.y
        if px > l and px < l + w and py > t and py < t + h then return false end
        for _, e in ipairs(world) do
            if e.valid and overlaps(box(e)) then return false end
        end
        for tx = math.floor(l), math.floor(l + w - 0.01) do
            if water(tx) then return false end
        end
        return true
    end,
}}
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
    return pytest.importorskip("lupa.lua52")


@pytest.fixture()
def lua():
    rt = _lupa().LuaRuntime(unpack_returned_tuples=True)
    rt.execute(STUB_LUA)
    rt.execute("helpers = {}")
    g = rt.globals()
    g.helpers.table_to_json = lambda t: json.dumps(_to_py(t))
    g.helpers.json_to_table = lambda s: rt.table_from(json.loads(s), recursive=True)
    rt.execute(SERVER_LUA.read_text())
    return rt


def _call(lua, mode, payload):
    hexed = json.dumps(payload).encode().hex()
    out = lua.globals().storage.actions.place_layout(1, mode, hexed)
    return json.loads(bytes.fromhex(out.strip('"')).decode())


def _list(v):
    return v if isinstance(v, list) else []


class _Rcon:
    def __init__(self, lua):
        self.lua = lua

    def send_command(self, cmd):
        assert "game.tick" in cmd
        return str(int(self.lua.eval("game.tick")))


def _tool(lua, walk_fails_at=None):
    """The client with execute and move_to running against the stub Lua state."""
    tool = object.__new__(PlaceLayout)
    tool.player_index = 1
    tool.game_state = SimpleNamespace(player_location=Position(x=0.5, y=0.5))
    tool.connection = SimpleNamespace(rcon_client=_Rcon(lua))
    walks = []

    def execute(player_index, mode, hexed):
        out = lua.globals().storage.actions.place_layout(player_index, mode, hexed)
        return out, 0

    def move_to(p):
        walks.append((p.x, p.y))
        if walk_fails_at is not None and len(walks) == walk_fails_at:
            raise Exception("Could not get path")
        lua.execute(
            f"player.position = {{x = {p.x}, y = {p.y}}}; game.tick = game.tick + 60"
        )
        return p

    tool.execute = execute
    tool.move_to = move_to
    tool.walks = walks
    return tool


COLUMN = [
    {"entity": Prototype.StoneFurnace, "x": 0, "y": 0},
    {
        "entity": Prototype.BurnerInserter,
        "x": -1.5,
        "y": -0.5,
        "direction": Direction.RIGHT,
    },
    (Prototype.TransportBelt, -2.5, -0.5, Direction.DOWN),
]


def test_lua_compiles():
    _lupa().LuaRuntime().compile(SERVER_LUA.read_text())


def test_plan_six_copies_all_ok_and_reachable(lua):
    plan = _call(
        lua,
        "plan",
        {
            "anchor": {"x": 10, "y": 4},
            "copies": 6,
            "offset": {"x": 0, "y": 2},
            "entries": [
                {"name": "stone-furnace", "x": 0, "y": 0, "dir": 0},
                {"name": "burner-inserter", "x": -1.5, "y": -0.5, "dir": 4},
                {"name": "transport-belt", "x": -2.5, "y": -0.5, "dir": 8},
            ],
        },
    )
    entries = plan["entries"]
    assert len(entries) == 18
    assert all(e["status"] == "ok" for e in entries), [
        e for e in entries if e["status"] != "ok"
    ]
    assert plan["required"] == {
        "stone-furnace": 6,
        "burner-inserter": 6,
        "transport-belt": 6,
    }
    assert plan["missing"] == {} or plan["missing"] == []
    # furnace k sits at (10, 4 + 2k): the game's centre for a 2x2 entity
    furnaces = [e for e in entries if e["name"] == "stone-furnace"]
    assert [(f["x"], f["y"]) for f in furnaces] == [(10, 4 + 2 * k) for k in range(6)]
    # every entity is in exactly one stop, within reach - 1 of it, and no stop is inside the layout
    stops = plan["stops"]
    seen = []
    for s in stops:
        for i in s["entries"]:
            e = entries[i - 1]
            assert ((e["x"] - s["x"]) ** 2 + (e["y"] - s["y"]) ** 2) ** 0.5 <= 9
            seen.append(i)
        assert not (8.5 < s["x"] < 11 and 2.5 < s["y"] < 15.5), s
    assert sorted(seen) == list(range(1, 19))


def test_plan_reports_overlap_inside_the_layout(lua):
    plan = _call(
        lua,
        "plan",
        {
            "anchor": {"x": 0, "y": 10},
            "entries": [
                {"name": "stone-furnace", "x": 0, "y": 0, "dir": 0},
                {"name": "transport-belt", "x": 0.5, "y": 0.5, "dir": 0},
            ],
        },
    )
    a, b = plan["entries"]
    assert a["status"] == "ok"
    assert b["status"] == "blocked"
    assert b["reason"] == "overlaps layout entry 1 (stone-furnace at (0, 10))"


def test_plan_reports_entities_water_and_ungenerated_map(lua):
    plan = _call(
        lua,
        "plan",
        {
            "anchor": {"x": 0, "y": 0},
            "entries": [
                {"name": "transport-belt", "x": 5.5, "y": -2.5, "dir": 0},  # the tree
                {
                    "name": "stone-furnace",
                    "x": 40,
                    "y": 0,
                    "dir": 0,
                },  # water at x >= 40
                {"name": "transport-belt", "x": 0.5, "y": 70.5, "dir": 0},
            ],
        },
    )  # not generated
    tree, wet, far = plan["entries"]
    assert tree["reason"] == "blocked by tree-01 at (5.5, -2.5)"
    assert wet["reason"].startswith("blocked by water at (40, ")
    assert (
        far["reason"]
        == "tile (0, 70) is in a part of the map that has not been generated or charted"
    )
    assert plan["problems"] == 3


def test_plan_counts_missing_items(lua):
    plan = _call(
        lua,
        "plan",
        {
            "anchor": {"x": 0, "y": 10},
            "copies": 6,
            "offset": {"x": 4, "y": 0},
            "entries": [{"name": "assembling-machine-1", "x": 0, "y": 0, "dir": 0}],
        },
    )
    assert plan["required"] == {"assembling-machine-1": 6}
    assert plan["have"] == {"assembling-machine-1": 5}
    assert plan["missing"] == {"assembling-machine-1": 1}


def test_settings_are_checked(lua):
    plan = _call(
        lua,
        "plan",
        {
            "anchor": {"x": 0, "y": 10},
            "entries": [
                {
                    "name": "assembling-machine-1",
                    "x": 0,
                    "y": 0,
                    "dir": 0,
                    "recipe": "electronic-circuit",
                },
                {
                    "name": "stone-furnace",
                    "x": 4,
                    "y": 0,
                    "dir": 0,
                    "recipe": "iron-gear-wheel",
                },
                {
                    "name": "burner-inserter",
                    "x": 6.5,
                    "y": 0.5,
                    "dir": 0,
                    "filter": "coal",
                },
                {
                    "name": "transport-belt",
                    "x": 7.5,
                    "y": 0.5,
                    "dir": 0,
                    "ugtype": "input",
                },
                {"name": "rocket", "x": 8.5, "y": 0.5, "dir": 0},
            ],
        },
    )
    reasons = [e.get("reason") for e in plan["entries"]]
    assert reasons == [
        "recipe electronic-circuit is not unlocked yet (research needed)",
        "stone-furnace has no recipe to set (only assembling machines do)",
        "burner-inserter has no filter slots",
        "type (input/output) is only for underground belts, not transport-belt",
        "rocket isn't an entity or an item that places one",
    ]
    assert all(e["status"] == "invalid" for e in plan["entries"])


def test_grid_with_legend(lua):
    plan = _call(
        lua,
        "plan",
        {
            "anchor": {"x": 0.3, "y": 20.7},
            "grid": {
                "rows": ["FF.", "FF>", "FFFF", "FFFF"],
                "legend": {
                    "F": {"name": "stone-furnace", "dir": 0},
                    ">": {"name": "transport-belt", "dir": 4},
                },
            },
        },
    )
    got = [(e["name"], e["x"], e["y"], e["dir"]) for e in plan["entries"]]
    assert got == [
        ("stone-furnace", 1, 21, 0),
        ("transport-belt", 2.5, 21.5, 4),
        ("stone-furnace", 1, 23, 0),
        ("stone-furnace", 3, 23, 0),
    ]
    assert all(e["status"] == "ok" for e in plan["entries"])


def test_grid_character_not_in_legend_is_an_error(lua):
    with pytest.raises(Exception, match="grid character 'X'"):
        _call(
            lua,
            "plan",
            {
                "anchor": {"x": 0, "y": 0},
                "grid": {"rows": ["X"], "legend": {"F": {"name": "stone-furnace"}}},
            },
        )


def test_place_uses_items_sets_recipe_filter_and_underground_type(lua):
    lua.execute("player.position = {x = 0.5, y = 12.5}")
    out = _call(
        lua,
        "place",
        {
            "entries": [
                {
                    "i": 1,
                    "name": "assembling-machine-1",
                    "item": "assembling-machine-1",
                    "x": 2.5,
                    "y": 10.5,
                    "dir": 0,
                    "recipe": "iron-gear-wheel",
                },
                {
                    "i": 2,
                    "name": "fast-inserter",
                    "item": "fast-inserter",
                    "x": 4.5,
                    "y": 10.5,
                    "dir": 4,
                    "filter": "coal",
                },
                {
                    "i": 3,
                    "name": "underground-belt",
                    "item": "underground-belt",
                    "x": 5.5,
                    "y": 10.5,
                    "dir": 4,
                    "ugtype": "output",
                },
                {
                    "i": 4,
                    "name": "transport-belt",
                    "item": "transport-belt",
                    "x": 30.5,
                    "y": 10.5,
                    "dir": 0,
                },
            ]
        },
    )
    st = {e["i"]: (e["status"], e.get("reason")) for e in out["entries"]}
    assert st[1] == ("placed", None)
    assert st[2] == ("placed", None)
    assert st[3] == ("placed", None)
    assert st[4] == ("failed", "out of reach (distance 30.07, reach 10)")
    g = lua.globals()
    assert g.player.inv["assembling-machine-1"] == 4
    assert g.player.inv["underground-belt"] == 3
    assert g.player.inv["transport-belt"] == 100
    machine = [e for e in g.world.values() if e.name == "assembling-machine-1"][0]
    assert machine.recipe == "iron-gear-wheel"
    ins = [e for e in g.world.values() if e.name == "fast-inserter"][0]
    assert ins.filter == "coal" and ins.use_filters
    ug = [s for s in g.created.values() if s.name == "underground-belt"][0]
    assert ug.type == "output" and ug.direction == 4


def test_place_without_item_fails(lua):
    lua.execute(
        "player.position = {x = 0.5, y = 12.5}; player.inv['transport-belt'] = 0"
    )
    out = _call(
        lua,
        "place",
        {
            "entries": [
                {
                    "i": 1,
                    "name": "transport-belt",
                    "item": "transport-belt",
                    "x": 2.5,
                    "y": 10.5,
                    "dir": 0,
                }
            ]
        },
    )
    assert out["entries"][0]["status"] == "failed"
    assert out["entries"][0]["reason"] == "no transport-belt in the inventory"


def test_client_builds_column_walks_and_reports(lua):
    tool = _tool(lua)
    res = tool(COLUMN, Position(x=10, y=4), copies=6, offset=Position(x=0, y=2))
    assert isinstance(res, LayoutResult)
    assert res.ok and bool(res)
    assert (res.total, res.placed, res.already_built) == (18, 18, 0)
    assert res.ticks == 60 * len(tool.walks) and len(tool.walks) == len(res.stops) >= 1
    g = lua.globals()
    assert g.player.inv["stone-furnace"] == 44
    assert g.player.inv["burner-inserter"] == 44
    assert res.character_position == Position(x=tool.walks[-1][0], y=tool.walks[-1][1])
    assert tool.game_state.player_location.x == tool.walks[-1][0]

    # same call again: everything is already built, no item used
    again = _tool(lua)(COLUMN, Position(x=10, y=4), copies=6, offset=Position(x=0, y=2))
    assert again.ok and again.already_built == 18 and again.placed == 0
    assert g.player.inv["stone-furnace"] == 44


def test_client_places_nothing_when_anything_fails(lua):
    tool = _tool(lua)
    layout = list(COLUMN) + [
        {"entity": Prototype.TransportBelt, "x": 30.5, "y": -6.5}
    ]  # tree at (5.5, -2.5)
    res = tool(layout, Position(x=-25, y=4))
    assert not res.ok and res.placed == 0
    assert res.reason == "nothing was placed: 1 of 4 entities cannot be placed"
    assert [p.reason for p in res.problems] == ["blocked by tree-01 at (5.5, -2.5)"]
    assert [e.status for e in res.entries] == ["would place"] * 3 + ["blocked"]
    assert tool.walks == []
    assert lua.globals().player.inv["stone-furnace"] == 50

    res = _tool(lua)(COLUMN, Position(x=10, y=4), copies=60, offset=Position(x=-4, y=0))
    assert not res.ok and res.missing == {"stone-furnace": 10, "burner-inserter": 10}
    assert (
        res.reason
        == "nothing was placed: missing items: burner-inserter x10, stone-furnace x10"
    )


def test_client_dry_run_builds_nothing(lua):
    tool = _tool(lua)
    res = tool(
        COLUMN, Position(x=10, y=4), copies=6, offset=Position(x=0, y=2), dry_run=True
    )
    assert res.ok and res.dry_run and res.placed == 0
    assert {e.status for e in res.entries} == {"would place"}
    assert res.walk_seconds_estimate > 0 and tool.walks == []
    assert lua.globals().player.inv["stone-furnace"] == 50


def test_client_partial_when_a_walk_fails_and_rerun_finishes(lua):
    far = Position(x=10, y=-20)
    tool = _tool(lua, walk_fails_at=2)
    res = tool(COLUMN, far, copies=12, offset=Position(x=0, y=2))
    assert len(res.stops) >= 2
    assert not res.ok and 0 < res.placed < 36
    assert "could not walk to stop 2" in res.reason
    left = [e for e in res.entries if e.status == "not placed"]
    assert left and all("could not walk to stop 2" in e.reason for e in left)
    res2 = _tool(lua)(COLUMN, far, copies=12, offset=Position(x=0, y=2))
    assert res2.ok and res2.placed == len(left) and res2.already_built == 36 - len(left)


def test_client_skips_an_unreachable_stop_and_builds_the_next(lua):
    """A failed walk used to end the call: every later stop stayed unbuilt."""
    far = Position(x=10, y=-20)
    tool = _tool(lua, walk_fails_at=2)
    res = tool(COLUMN, far, copies=30, offset=Position(x=0, y=2))
    n = len(res.stops)
    assert n >= 3
    assert len(tool.walks) == n  # it walked to every stop, the failed one included
    left = [e for e in res.entries if e.status == "not placed"]
    assert left and res.placed == 90 - len(left)
    assert all(e.reason.startswith("could not walk to stop 2 at (") for e in left)
    assert all("Could not get path" in e.reason for e in left)
    assert res.reason == f"{len(left)} of 90 entities were not placed (could not walk to stop 2 of {n})"
    # the character ends at the last stop it reached
    assert res.character_position == Position(x=tool.walks[-1][0], y=tool.walks[-1][1])


def test_client_max_seconds_stops_before_walking(lua):
    tool = _tool(lua)
    res = tool(
        COLUMN, Position(x=10, y=4), copies=6, offset=Position(x=0, y=2), max_seconds=0
    )
    assert not res.ok and res.placed == 0 and tool.walks == []
    assert "max_seconds=0 reached" in res.reason


def test_client_input_errors():
    tool = object.__new__(PlaceLayout)
    with pytest.raises(ValueError, match="unknown key"):
        tool([{"entity": Prototype.StoneFurnace, "dir": 1}], Position(x=0, y=0))
    with pytest.raises(ValueError, match="non-zero offset"):
        tool(COLUMN, Position(x=0, y=0), copies=2)
    with pytest.raises(ValueError, match="not in the legend"):
        tool("FX", Position(x=0, y=0), legend={"F": Prototype.StoneFurnace})
    with pytest.raises(ValueError, match="at most 1000"):
        tool(COLUMN, Position(x=0, y=0), copies=400, offset=Position(x=0, y=2))
    with pytest.raises(ValueError, match="direction must be a Direction"):
        tool([(Prototype.StoneFurnace, 0, 0, "up")], Position(x=0, y=0))


def test_result_repr_lists_problems():
    from fle.env.entities import LayoutEntry

    r = LayoutResult(
        ok=False,
        total=2,
        reason="nothing was placed: 1 of 2 entities cannot be placed",
        problems=[
            LayoutEntry(
                index=2,
                name="stone-furnace",
                position=Position(x=1, y=1),
                status="blocked",
                reason="blocked by water at (1, 1)",
            )
        ],
    )
    text = repr(r)
    assert text.startswith("LayoutResult(ok=False, total=2, placed=0")
    assert "#2 stone-furnace at (1.0, 1.0) blocked: blocked by water at (1, 1)" in text
    assert not r


def test_long_column_needs_few_stops(lua):
    lua.execute(
        "player.inv['stone-furnace'] = 100; player.inv['burner-inserter'] = 100"
    )
    plan = _call(
        lua,
        "plan",
        {
            "anchor": {"x": 10, "y": -60},
            "copies": 24,
            "offset": {"x": 0, "y": 2},
            "entries": [
                {"name": "stone-furnace", "x": 0, "y": 0, "dir": 0},
                {"name": "burner-inserter", "x": -1.5, "y": -0.5, "dir": 4},
            ],
        },
    )
    assert all(e["status"] == "ok" for e in plan["entries"])
    stops = plan["stops"]
    assert len(stops) <= 4
    assert len({(s["x"], s["y"]) for s in stops}) == len(stops)
    assert sorted(i for s in stops for i in s["entries"]) == list(range(1, 49))
