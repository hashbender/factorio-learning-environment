"""place_entity returns the entity it built, not a neighbour of the same name (no server).

The Lua action runs in lupa (Lua 5.2, as Factorio) against a stub surface.

Regression: after create_entity, place_entity searched a 1-tile margin around the
position for an entity of the same name and returned the first one found. With an
inserter already on the next tile (a row of inserters beside a 3x3 machine), it
returned that inserter: its position, direction and pickup / drop targets, so the
caller saw a drop target that the new inserter did not have.
"""

from pathlib import Path

import pytest

SERVER_LUA = (
    Path(__file__).resolve().parents[2] / "fle/env/tools/agent/place_entity/server.lua"
)

STUB_LUA = """
defines = {direction = {north = 0, east = 4, south = 8, west = 12}}
prototypes = {entity = {}, item = {}}
for _, n in ipairs({"inserter", "wooden-chest"}) do
    prototypes.entity[n] = {name = n, tile_width = 1, tile_height = 1,
        collision_box = {left_top = {x = -0.15, y = -0.15}, right_bottom = {x = 0.15, y = 0.15}}}
end
rendering = {draw_circle = function() end, draw_rectangle = function() end}
world = {}
local next_id = 1
local surface = {}
function surface.find_entity(name, p)
    for _, e in ipairs(world) do
        if e.name == name and e.position.x == p.x and e.position.y == p.y then return e end
    end
end
function surface.find_entities_filtered(f)
    local out = {}
    for _, e in ipairs(world) do
        local x, y = e.position.x, e.position.y
        if (f.name == nil or f.name == e.name) and f.area
            -- collision boxes (0.3 x 0.3) that overlap the area, as the game matches them
            and x + 0.15 > f.area[1][1] and x - 0.15 < f.area[2][1]
            and y + 0.15 > f.area[1][2] and y - 0.15 < f.area[2][2] then
            table.insert(out, e)
        end
    end
    return out
end
function surface.get_tile() return {name = "grass-1"} end
function surface.create_entity(spec)
    local e = {valid = true, name = spec.name, type = spec.name, unit_number = next_id,
               position = {x = spec.position.x, y = spec.position.y}, direction = spec.direction}
    next_id = next_id + 1
    table.insert(world, e)
    return e
end
player = {valid = true, surface = surface, force = {name = "player"}, position = {x = 1, y = 18},
          reach_distance = 10}
function player.get_item_count() return 10 end
function player.remove_item() return 1 end
storage = {fast = true, actions = {}, utils = {
    ensure_valid_character = function() return player end,
    get_entity_direction = function(_, d) return d end,
    avoid_entity = function() end,
    can_place_entity = function(_, name, p)
        return surface.find_entity(name, p) == nil
    end,
    revive_ghost = function() return nil end,
    serialize_entity = function(e)
        return {name = e.name, unit_number = e.unit_number, x = e.position.x, y = e.position.y,
                direction = e.direction}
    end,
    note_dropped_direction = function(s) return s end,
    format_inventory_for_error = function() return "" end,
}}
function place(name, direction, x, y, exact)
    local r = storage.actions.place_entity(1, name, direction, x, y, exact)
    return r.unit_number, r.x, r.y, r.direction
end
"""


@pytest.fixture()
def lua():
    lupa = pytest.importorskip("lupa.lua52")
    rt = lupa.LuaRuntime(unpack_returned_tuples=True)
    rt.execute(STUB_LUA)
    rt.execute(SERVER_LUA.read_text())
    return rt


def test_second_inserter_in_a_row_returns_itself(lua):
    place = lua.globals().place
    first = place("inserter", 4, 2.5, 19.5, True)
    second = place(
        "inserter", 12, 2.5, 20.5, True
    )  # next tile down, facing the other way
    assert first == (1, 2.5, 19.5, 4)
    assert second == (2, 2.5, 20.5, 12)


def test_inserter_placed_above_a_neighbour_returns_itself(lua):
    place = lua.globals().place
    place("inserter", 4, 2.5, 20.5, True)
    assert place("inserter", 0, 2.5, 19.5, True) == (2, 2.5, 19.5, 0)


def test_moved_placement_returns_the_built_entity(lua):
    # not exact and the tile is taken: the entity is built on a free tile nearby,
    # and that entity is returned
    place = lua.globals().place
    place("wooden-chest", 0, 0.5, 17.5, True)
    uid, x, y, _ = place("wooden-chest", 0, 0.5, 17.5, False)
    assert uid == 2
    assert (x, y) != (0.5, 17.5)
