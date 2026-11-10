"""can_place_entity reports the game's answer and what is in the way. Server-free.

The action is run in Lua (lupa) against a stub surface; the client is run with
execute stubbed."""

from pathlib import Path

import pytest

from fle.env.entities import Direction, PlacementCheck, Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.can_place_entity.client import CanPlaceEntity

SERVER_LUA = (
    Path(__file__).resolve().parents[2]
    / "fle/env/tools/agent/can_place_entity/server.lua"
)

# A stub map: a pipe on tile (5, 5), water on tiles x >= 10, a tree on (7, 5),
# crude oil under (20.5, 20.5); chunks with x >= 2 (tiles 64+) are not charted.
# The stub build check refuses any footprint that touches a blocker, and the
# character while it stands in the footprint.
STUB_LUA = """
defines = {direction = {north = 0, east = 4, south = 8, west = 12}}
local function proto(type, w, h, layers, extra)
    local p = {type = type, tile_width = w, tile_height = h,
               collision_box = {left_top = {x = -w / 2 + 0.1, y = -h / 2 + 0.1},
                                right_bottom = {x = w / 2 - 0.1, y = h / 2 - 0.1}},
               collision_mask = {layers = layers}}
    for k, v in pairs(extra or {}) do p[k] = v end
    return p
end
local building = {object = true, water_tile = true, player = true}
prototypes = {
    item = {rail = {place_result = {name = "straight-rail"}}},
    entity = {
        ["stone-furnace"] = proto("furnace", 2, 2, building),
        ["transport-belt"] = proto("transport-belt", 1, 1, {object = true, water_tile = true, transport_belt = true}),
        ["steam-engine"] = proto("generator", 3, 5, building),
        ["pipe"] = proto("pipe", 1, 1, building),
        ["tree-01"] = proto("tree", 1, 1, {object = true, player = true}),
        ["item-on-ground"] = proto("item-entity", 1, 1, {item = true}),
        ["pumpjack"] = proto("mining-drill", 3, 3, building, {resource_categories = {["basic-fluid"] = true}}),
        ["offshore-pump"] = proto("offshore-pump", 1, 1, {object = true}),
        ["straight-rail"] = proto("straight-rail", 2, 2, {rail = true}),
        ["crude-oil"] = proto("resource", 1, 1, {resource = true}, {resource_category = "basic-fluid"}),
        ["iron-ore"] = proto("resource", 1, 1, {resource = true}, {resource_category = "basic-solid"}),
    },
}
local function ent(name, x, y)
    return {valid = true, name = name, type = prototypes.entity[name].type,
            position = {x = x, y = y}, prototype = prototypes.entity[name]}
end
world = {ent("pipe", 5.5, 5.5), ent("tree-01", 7.5, 5.5), ent("item-on-ground", 3.5, 3.5),
         ent("crude-oil", 20.5, 20.5)}
teleports = {}
player = {valid = true, position = {x = 0.5, y = 0.5}, reach_distance = 10, items = {["stone-furnace"] = 2},
          force = {is_chunk_charted = function(s, chunk) return chunk.x < 2 end}}
player.get_item_count = function(name) return player.items[name] or 0 end
player.teleport = function(p)
    table.insert(teleports, {x = p.x, y = p.y})
    player.position = {x = p.x, y = p.y}
end
local function water(tx) return tx >= 10 and tx < 64 end
local function inside(f, x, y)
    return x >= f.area[1][1] and x <= f.area[2][1] and y >= f.area[1][2] and y <= f.area[2][2]
end
local surface = {
    find_entities_filtered = function(f)
        local out = {}
        for _, e in ipairs(world) do
            if inside(f, e.position.x, e.position.y) then table.insert(out, e) end
        end
        return out
    end,
    get_tile = function(tx, ty)
        local name = water(tx) and "water" or "grass-1"
        return {valid = true, name = name,
                collides_with = function(layer) return name == "water" and layer == "water_tile" end}
    end,
}
player.surface = surface
storage = {actions = {}, agent_characters = {player}, utils = {
    get_entity_direction = function(entity, direction) return direction end,
    ensure_valid_character = function() return player end,
    can_place_entity = function(p, entity, position, direction)
        local pr = prototypes.entity[entity]
        local w, h = pr.tile_width, pr.tile_height
        if direction == 4 or direction == 12 then w, h = h, w end
        local l, t = position.x - w / 2, position.y - h / 2
        local function hit(x, y) return x > l and x < l + w and y > t and y < t + h end
        if hit(player.position.x, player.position.y) then return false end
        if entity == "pumpjack" then return hit(20.5, 20.5) end
        if entity == "offshore-pump" then return false end
        for _, e in ipairs(world) do
            if e.type ~= "item-entity" and e.type ~= "resource" and hit(e.position.x, e.position.y) then
                return false
            end
        end
        for tx = math.floor(l), math.floor(l + w - 0.01) do
            if water(tx) then return false end
        end
        return true
    end,
}}
"""


def _run(entity, direction, x, y, setup=""):
    lupa = pytest.importorskip("lupa")
    lua = lupa.LuaRuntime()
    lua.execute(STUB_LUA)
    lua.execute(setup)
    lua.execute(SERVER_LUA.read_text())
    result = lua.eval("storage.actions.can_place_entity")(1, entity, direction, x, y)
    return lua, result


def _blockers(result):
    return [
        (
            result.blocked_by[i].kind.strip('"'),
            result.blocked_by[i].name.strip('"'),
            result.blocked_by[i].x,
            result.blocked_by[i].y,
        )
        for i in range(1, len(result.blocked_by) + 1)
    ]


def test_fits_on_free_ground():
    _, r = _run("stone-furnace", 0, 3, 3)
    assert r.fits and r.can_place and r.in_reach
    assert r.reason is None
    assert (r.position.x, r.position.y) == (3, 3)  # a 2x2 entity sits on a tile corner
    assert (r.footprint.left, r.footprint.top, r.footprint.right, r.footprint.bottom) == (2, 2, 3, 3)
    assert r.in_inventory == 2
    assert r.blocked_count == 0


def test_blocked_by_an_entity_names_it_and_its_position():
    _, r = _run("stone-furnace", 0, 5, 5)
    assert not r.fits and not r.can_place
    assert r.reason == '"blocked by pipe at (5.5, 5.5)"'
    assert _blockers(r) == [("entity", "pipe", 5.5, 5.5)]


def test_blocked_by_water_names_the_tiles():
    _, r = _run("stone-furnace", 0, 10, 3)
    assert not r.fits
    # the footprint is tiles x 9..10, y 2..3; x = 10 is water
    assert _blockers(r) == [("tile", "water", 10, 2), ("tile", "water", 10, 3)]
    assert r.reason == '"blocked by water at (10, 2), water at (10, 3)"'


def test_at_most_five_blockers_are_listed_with_the_total():
    _, r = _run("steam-engine", 0, 12.5, 5.5)
    assert r.blocked_count == 15
    assert len(_blockers(r)) == 5
    assert r.reason.endswith('and 10 more"')


def test_tree_blocks_and_items_on_the_ground_do_not():
    _, r = _run("transport-belt", 4, 7.5, 5.5)
    assert _blockers(r) == [("entity", "tree-01", 7.5, 5.5)]
    _, r = _run("transport-belt", 4, 3.5, 3.5)
    assert r.fits


def test_uncharted_position():
    _, r = _run("stone-furnace", 0, 140, -62)
    assert not r.fits
    assert r.reason == '"tile (139, -63) is outside the charted map"'
    assert r.blocked_count == 0


def test_pumpjack_needs_its_resource():
    _, r = _run("pumpjack", 0, 3.5, 3.5)
    assert not r.fits
    assert r.reason == (
        '"pumpjack must be placed on a resource it can mine (crude-oil); '
        'there is none under this position"'
    )
    _, r = _run("pumpjack", 0, 20.5, 20.5)
    assert r.fits


def test_offshore_pump_rule():
    _, r = _run("offshore-pump", 0, 3.5, 3.5)
    assert r.reason == '"offshore-pump must be placed at the edge of water, facing the water"'


def test_reach_and_inventory_are_reported_not_required():
    _, r = _run("transport-belt", 0, 3.5, 40.5)
    assert r.fits  # the game's answer does not depend on reach or on holding the item
    assert not r.in_reach and r.in_inventory == 0 and not r.can_place
    assert r.reach == 10 and r.distance == 40.11


def test_character_in_the_footprint_is_stepped_aside_and_put_back():
    lua, r = _run("stone-furnace", 0, 1, 1)
    assert r.fits
    teleports = lua.eval("teleports")
    assert len(teleports) == 2
    assert (teleports[2].x, teleports[2].y) == (0.5, 0.5)
    assert (lua.eval("player.position.x"), lua.eval("player.position.y")) == (0.5, 0.5)


def test_character_is_not_moved_otherwise():
    lua, _ = _run("stone-furnace", 0, 5, 5)
    assert len(lua.eval("teleports")) == 0


def test_item_that_builds_another_entity():
    _, r = _run("rail", 0, 3, 3, setup='player.items["rail"] = 7')
    assert r.fits and r.in_inventory == 7


def test_unknown_entity_is_an_error():
    lupa = pytest.importorskip("lupa")
    with pytest.raises(lupa.LuaError) as e:
        _run("stone-furnase", 0, 3, 3)
    assert "isn't a valid entity prototype" in str(e.value)


# --- client ----------------------------------------------------------------------------------------


def _tool(response):
    tool = CanPlaceEntity.__new__(CanPlaceEntity)
    tool.player_index = 1
    tool.execute = lambda *args: (response, 0)
    return tool


BASE = {
    "position": {"x": 9.5, "y": 3.5},
    "fits": True,
    "can_place": True,
    "in_reach": True,
    "distance": 2.5,
    "reach": 10,
    "in_inventory": 40,
    "blocked_by": {},
    "blocked_count": 0,
}


def test_client_true_result():
    check = _tool(BASE)(Prototype.TransportBelt, Direction.RIGHT, Position(x=9.5, y=3.5))
    assert isinstance(check, PlacementCheck)
    assert check and check.can_place and check.fits and check.reason is None
    assert repr(check) == (
        "PlacementCheck(can_place=True, entity=transport-belt, position=(9.5, 3.5), "
        "direction=RIGHT, fits=True, in_reach=True, in_inventory=40)"
    )


def test_client_blocked_result_is_false_and_names_the_blocker():
    resp = dict(
        BASE,
        fits=False,
        can_place=False,
        reason="blocked by pipe at (9.5, 3.5)",
        blocked_by={1: {"kind": "entity", "name": "pipe", "x": 9.5, "y": 3.5}},
        blocked_count=1,
    )
    check = _tool(resp)(Prototype.TransportBelt, Direction.RIGHT, Position(x=9.5, y=3.5))
    assert not check
    assert check.blocked_by[0].name == "pipe"
    assert check.blocked_by[0].position == Position(x=9.5, y=3.5)
    assert repr(check) == (
        "PlacementCheck(can_place=False, entity=transport-belt, position=(9.5, 3.5), "
        "direction=RIGHT, fits=False, reason='blocked by pipe at (9.5, 3.5)', "
        "blocked_by=[pipe at (9.5, 3.5)], in_reach=True, in_inventory=40)"
    )


def test_client_fits_but_cannot_be_placed_now():
    resp = dict(BASE, in_reach=False, distance=14.2, in_inventory=0)
    check = _tool(resp)(Prototype.StoneFurnace, Direction.UP, Position(x=9.5, y=3.5))
    assert not check and check.fits
    assert check.reason == (
        "fits, but out of reach (distance 14.2, reach 10) and no stone-furnace in your inventory"
    )
    check = _tool(dict(BASE, in_inventory=0))(Prototype.StoneFurnace)
    assert check.reason == "fits, but no stone-furnace in your inventory"


def test_client_reports_an_action_error():
    with pytest.raises(Exception) as e:
        _tool('[string "x"]:3: "boom"')(Prototype.StoneFurnace)
    assert str(e.value) == "Could not check placement of stone-furnace: boom"
