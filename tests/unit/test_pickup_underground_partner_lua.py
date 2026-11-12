"""pickup_entity's partner lookup for an underground belt is a Lua query sent over RCON
(LuaEntity.neighbours). Here that exact query runs in lupa against a small map, so a broken
query (wrong field, wrong filter, wrong output format) fails, and the pair/lone-end answers
of the whole call follow from it."""

import pytest

from fle.env import entities as ent
from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.pickup_entity.client import PickupEntity

lupa = pytest.importorskip("lupa")

MAP = """
ents = {}
picked = {}
local function add(name, x, y) local e = {valid = true, name = name, position = {x = x, y = y}}; ents[#ents + 1] = e; return e end
local a = add("underground-belt", 6.5, 40.5)
local b = add("underground-belt", 6.5, 36.5)
a.neighbours = b; b.neighbours = a
add("underground-belt", 10.5, 40.5)                    -- an end with no pair
add("fast-underground-belt", 6.5, 38.5)                -- another tier between them
out = {}
rcon = {print = function(s) out[#out + 1] = tostring(s) end}
local surface = {}
function surface.find_entities_filtered(f)
    local r = {}
    for _, e in ipairs(ents) do
        if e.valid and (f.name == nil or f.name == e.name)
            and math.abs(e.position.x - f.position[1]) <= (f.radius or 0)
            and math.abs(e.position.y - f.position[2]) <= (f.radius or 0) then r[#r + 1] = e end
    end
    return r
end
game = {surfaces = {[1] = surface}}
function pick(name, x, y)
    for _, e in ipairs(ents) do
        if e.valid and e.name == name and e.position.x == x and e.position.y == y then
            e.valid = false; picked[#picked + 1] = name .. "@" .. x .. "," .. y; return 1
        end
    end
    return "no " .. name .. " at " .. x .. "," .. y
end
"""


class _Rcon:
    def __init__(self, lua):
        self.lua = lua

    def send_command(self, cmd):
        assert cmd.startswith("/sc ")
        self.lua.execute("out = {}")
        self.lua.execute(cmd[4:])
        return "\n".join(self.lua.eval("out").values())


class _Conn:
    def __init__(self, lua):
        self.rcon_client = _Rcon(lua)


def _tool():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(MAP)
    tool = PickupEntity.__new__(PickupEntity)
    tool.connection = _Conn(lua)
    tool.player_index = 1
    tool.check_reach = True
    tool.get_error_message = lambda m: str(m)
    tool.execute = lambda idx, x, y, name, reach: (lua.eval("pick")(name, x, y), 0)
    return tool, lua


def _picked(lua):
    return sorted(lua.eval("picked").values())


def test_the_query_finds_the_linked_end():
    tool, _ = _tool()
    assert tool._underground_partner("underground-belt", 6.5, 40.5) == (6.5, 36.5)
    assert tool._underground_partner("underground-belt", 6.5, 36.5) == (6.5, 40.5)


def test_the_query_finds_nothing_for_an_unpaired_end_or_an_empty_tile():
    tool, _ = _tool()
    assert tool._underground_partner("underground-belt", 10.5, 40.5) is None
    assert tool._underground_partner("underground-belt", 20.5, 40.5) is None


def test_by_prototype_and_position_a_linked_pair_goes_together():
    tool, lua = _tool()
    r = tool(Prototype.UndergroundBelt, Position(x=6.5, y=40.5))
    assert r and "its paired underground-belt at (6.5, 36.5)" in repr(r)
    assert _picked(lua) == ["underground-belt@6.5,36.5", "underground-belt@6.5,40.5"]


def test_by_entity_a_linked_pair_goes_together_and_a_lone_end_alone():
    tool, lua = _tool()
    belt = ent.UndergroundBelt.model_construct(
        name="underground-belt", position=Position(x=6.5, y=36.5), is_input=False
    )
    assert tool(belt)
    lone = ent.UndergroundBelt.model_construct(
        name="underground-belt", position=Position(x=10.5, y=40.5), is_input=True
    )
    r = tool(lone)
    assert r and "paired" not in repr(r)
    assert _picked(lua) == ["underground-belt@10.5,40.5", "underground-belt@6.5,36.5", "underground-belt@6.5,40.5"]
    # the other tier between them is untouched
    assert tool._underground_partner("fast-underground-belt", 6.5, 38.5) is None
