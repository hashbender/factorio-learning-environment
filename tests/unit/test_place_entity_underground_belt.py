"""place_entity builds underground belts as the end that pairs (no server).

The Lua action runs in lupa (Lua 5.2, as Factorio) against a stub surface.

Regression: place_entity called create_entity without `type`, and the game then builds
an input end, so two underground belts placed one at a time were both inputs and never
connected. Now, as when a player places one, a belt behind which (within reach) stands an
unpaired input end of the same kind travelling the same way is built as the output end;
`type="input"` / `"output"` chooses the end explicitly.
"""

from pathlib import Path

import pytest

SERVER_LUA = (
    Path(__file__).resolve().parents[2] / "fle/env/tools/agent/place_entity/server.lua"
)

STUB_LUA = """
defines = {direction = {north = 0, east = 4, south = 8, west = 12}}
prototypes = {entity = {}, item = {}}
local box = {left_top = {x = -0.4, y = -0.4}, right_bottom = {x = 0.4, y = 0.4}}
for n, reach in pairs({["underground-belt"] = 5, ["fast-underground-belt"] = 7}) do
    prototypes.entity[n] = {name = n, type = "underground-belt", tile_width = 1, tile_height = 1,
        max_underground_distance = reach, collision_box = box}
end
prototypes.entity["wooden-chest"] = {name = "wooden-chest", type = "container", tile_width = 1,
    tile_height = 1, collision_box = box}
rendering = {draw_circle = function() end, draw_rectangle = function() end}
world = {}
specs = {}
local next_id = 1
local surface = {}
local function at(e, p) return e.position.x == p.x and e.position.y == p.y end
function surface.find_entity(name, p)
    for _, e in ipairs(world) do
        if e.name == name and at(e, p) then return e end
    end
end
function surface.find_entities_filtered(f)
    local out = {}
    for _, e in ipairs(world) do
        if (f.name == nil or f.name == e.name) and (f.position == nil or at(e, f.position)) then
            table.insert(out, e)
        end
    end
    return out
end
function surface.get_tile() return {name = "grass-1"} end
local STEP = {[0] = {0, -1}, [4] = {1, 0}, [8] = {0, 1}, [12] = {-1, 0}}
function surface.create_entity(spec)
    table.insert(specs, spec)
    local e = {valid = true, name = spec.name, type = prototypes.entity[spec.name].type,
               unit_number = next_id, position = {x = spec.position.x, y = spec.position.y},
               direction = spec.direction}
    next_id = next_id + 1
    if e.type == "underground-belt" then
        e.belt_to_ground_type = spec.type or "input"
        -- the game pairs an output with the nearest input behind it (same name and direction)
        if e.belt_to_ground_type == "output" then
            local s = STEP[e.direction]
            for k = 1, prototypes.entity[e.name].max_underground_distance do
                local p = {x = e.position.x - s[1] * k, y = e.position.y - s[2] * k}
                local o = surface.find_entities_filtered{position = p, name = e.name}[1]
                if o and o.direction == e.direction then
                    if o.belt_to_ground_type == "input" then o.neighbours = e; e.neighbours = o end
                    break
                end
            end
        end
    end
    table.insert(world, e)
    return e
end
player = {valid = true, surface = surface, force = {name = "player"}, position = {x = 5, y = 5},
          reach_distance = 30}
function player.get_item_count() return 10 end
function player.remove_item() return 1 end
storage = {fast = true, actions = {}, utils = {
    ensure_valid_character = function() return player end,
    get_entity_direction = function(_, d) return d end,
    avoid_entity = function() end,
    can_place_entity = function(_, name, p) return surface.find_entity(name, p) == nil end,
    revive_ghost = function() return nil end,
    serialize_entity = function(e) return e end,
    note_dropped_direction = function(s) return s end,
    format_inventory_for_error = function() return "" end,
}}
function place(name, direction, x, y, belt_type)
    local e = storage.actions.place_entity(1, name, direction, x, y, true, belt_type)
    local partner = e.neighbours and e.neighbours.unit_number or nil
    return e.belt_to_ground_type, partner
end
"""


@pytest.fixture()
def lua():
    lupa = pytest.importorskip("lupa.lua52")
    rt = lupa.LuaRuntime(unpack_returned_tuples=True)
    rt.execute(STUB_LUA)
    rt.execute(SERVER_LUA.read_text())
    return rt


EAST, SOUTH, WEST, NORTH = 4, 8, 12, 0


def test_second_belt_ahead_of_an_input_is_the_output_and_pairs(lua):
    place = lua.globals().place
    assert place("underground-belt", EAST, 0.5, 0.5) == ("input", None)
    assert place("underground-belt", EAST, 5.5, 0.5) == ("output", 1)  # 5 tiles: max reach


@pytest.mark.parametrize("direction,dx,dy", [(NORTH, 0, -3), (SOUTH, 0, 3), (WEST, -3, 0)])
def test_every_direction(lua, direction, dx, dy):
    place = lua.globals().place
    place("underground-belt", direction, 0.5, 0.5)
    assert place("underground-belt", direction, 0.5 + dx, 0.5 + dy) == ("output", 1)


def test_beyond_reach_is_an_input(lua):
    place = lua.globals().place
    place("underground-belt", EAST, 0.5, 0.5)
    assert place("underground-belt", EAST, 6.5, 0.5) == ("input", None)


def test_fast_belt_reach_is_seven(lua):
    place = lua.globals().place
    place("fast-underground-belt", EAST, 0.5, 0.5)
    assert place("fast-underground-belt", EAST, 7.5, 0.5)[0] == "output"


def test_other_kind_or_direction_or_behind_does_not_pair(lua):
    place = lua.globals().place
    place("underground-belt", EAST, 0.5, 0.5)
    assert place("fast-underground-belt", EAST, 2.5, 0.5)[0] == "input"  # other kind
    assert place("underground-belt", WEST, 3.5, 0.5)[0] == "input"  # other direction
    assert place("underground-belt", EAST, -2.5, 0.5)[0] == "input"  # behind the input


def test_paired_input_is_not_taken_over(lua):
    place = lua.globals().place
    place("underground-belt", EAST, 0.5, 0.5)
    place("underground-belt", EAST, 4.5, 0.5)  # output, pairs with the first
    # nearest same-kind belt behind this one is the paired output: a new input
    assert place("underground-belt", EAST, 6.5, 0.5) == ("input", None)
    # between the pair: nearest behind is the paired input
    assert place("underground-belt", EAST, 2.5, 0.5) == ("input", None)


def test_explicit_type_wins(lua):
    place = lua.globals().place
    assert place("underground-belt", EAST, 0.5, 0.5, "output")[0] == "output"
    place("underground-belt", EAST, 10.5, 0.5)
    assert place("underground-belt", EAST, 12.5, 0.5, "input")[0] == "input"


def test_type_on_another_entity_or_bad_value_is_an_error(lua):
    place = lua.globals().place
    with pytest.raises(Exception, match="only for underground belts"):
        place("wooden-chest", NORTH, 0.5, 0.5, "input")
    with pytest.raises(Exception, match="type must be input or output"):
        place("underground-belt", EAST, 0.5, 0.5, "sideways")
    assert len(lua.globals().world) == 0


def test_non_underground_spec_has_no_type(lua):
    lua.globals().place("wooden-chest", NORTH, 0.5, 0.5)
    assert lua.globals().specs[1].type is None


def test_client_passes_type_only_when_given():
    from types import SimpleNamespace

    from fle.env.game_types import Prototype
    from fle.env.entities import Direction, Position
    from fle.env.tools.agent.place_entity.client import PlaceObject

    tool = object.__new__(PlaceObject)
    tool.player_index = 1
    tool.game_state = SimpleNamespace(instance=SimpleNamespace(fast=True))
    calls = []

    def execute(*args):
        calls.append(args)
        raise RuntimeError("stop here")

    tool.execute = execute
    tool.get_position = lambda p: (p.x, p.y)
    tool.get_error_message = str
    for kw in ({}, {"type": "output"}):
        with pytest.raises(Exception):
            tool(Prototype.UndergroundBelt, Direction.RIGHT, Position(x=1.5, y=1.5), **kw)
    assert len(calls[0]) == 6 and calls[1][-1] == "output"
    with pytest.raises(ValueError, match="type must be"):
        tool(Prototype.UndergroundBelt, Direction.RIGHT, Position(x=1.5, y=1.5), type="in")
