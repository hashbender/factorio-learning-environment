"""rotate_entity on crafting machines follows Factorio 2.0. Server-free (Lua via lupa).

The mock machine behaves like the game (checked on 2.0.73): assigning
direction is ignored by a machine without fluid boxes (assembling-machine-1)
and by assembling machines 2/3 unless their recipe uses a fluid; otherwise it
turns in place and keeps its contents.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

ROTATE_LUA = (
    Path(__file__).resolve().parents[2] / "fle/env/tools/agent/rotate_entity/server.lua"
)

MOCKS = """
destroyed = 0
function make_machine(name, fluidboxes, recipe, recipe_uses_fluid, turns_without_recipe)
    local state = {direction = 0}
    local m = {
        name = name, type = "assembling-machine", valid = true,
        position = {x = 0.5, y = 0.5},
        prototype = {fluidbox_prototypes = {}},
        get_recipe = function() return recipe and {name = recipe} or nil end,
        destroy = function() destroyed = destroyed + 1 end,
        teleport = function() end,
    }
    for i = 1, fluidboxes do m.prototype.fluidbox_prototypes[i] = {} end
    local takes_direction = fluidboxes > 0 and (recipe_uses_fluid or turns_without_recipe)
    return setmetatable(m, {
        __index = function(_, k) return state[k] end,
        __newindex = function(_, k, v)
            if k == "direction" then
                if takes_direction then state.direction = v end
            else
                rawset(m, k, v)
            end
        end,
    })
end
machine = nil
surface = {find_entities_filtered = function() return {machine} end}
game = {players = {}, surfaces = {surface}}
storage = {
    agent_characters = {{surface = surface, can_reach_entity = function() return true end}},
    utils = {
        get_entity_direction = function(name, d) return d end,
        serialize_entity = function(e) return {direction = e.direction} end,
    },
    actions = {},
}
"""


def _rotate(lua, *machine_args):
    lua.execute("destroyed = 0")
    lua.execute(
        "machine = make_machine(" + ", ".join(_lua_arg(a) for a in machine_args) + ")"
    )
    return lua.eval(
        "function() return storage.actions.rotate_entity(1, 0.5, 0.5, 4, machine.name, false) end"
    )


def _lua_arg(value):
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


@pytest.fixture
def lua():
    runtime = lupa.LuaRuntime()
    runtime.execute(MOCKS)
    runtime.execute(ROTATE_LUA.read_text())
    return runtime


def test_fluid_recipe_assembler_turns_in_place(lua):
    result = _rotate(lua, "assembling-machine-2", 2, "water-barrel", True, False)()
    assert result.direction == 4
    assert lua.eval("destroyed") == 0


def test_chemical_plant_turns_without_recipe(lua):
    result = _rotate(lua, "chemical-plant", 4, None, False, True)()
    assert result.direction == 4
    assert lua.eval("destroyed") == 0


def test_assembler_without_fluid_recipe_names_the_reason(lua):
    with pytest.raises(lupa.LuaError, match="iron-gear-wheel uses no fluid"):
        _rotate(lua, "assembling-machine-2", 2, "iron-gear-wheel", False, False)()


def test_assembler_without_recipe_names_the_reason(lua):
    with pytest.raises(lupa.LuaError, match="off while it has no recipe"):
        _rotate(lua, "assembling-machine-3", 2, None, False, False)()


def test_assembling_machine_1_never_turns(lua):
    with pytest.raises(lupa.LuaError, match="no fluid connections"):
        _rotate(lua, "assembling-machine-1", 0, "iron-gear-wheel", False, False)()
