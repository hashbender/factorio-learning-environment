"""place_entity says when Factorio 2.0 drops the requested direction. Server-free (Lua via lupa).

On a 2.0.73 server, create_entity{direction = east} gives an
assembling-machine-2/3 without a fluid recipe and an assembling-machine-1
(no fluid boxes) facing north; chemical plants and refineries face east.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

UTILS_LUA = Path(__file__).resolve().parents[2] / "fle/env/mods/utils.lua"

EAST = 4


@pytest.fixture
def note():
    lua = lupa.LuaRuntime()
    lua.execute(
        "defines = {direction = {north = 0, east = 4, south = 8, west = 12}}\n"
        "storage = {utils = {}}"
    )
    # utils.lua as a whole needs Factorio's Lua 5.2 (it assigns to a for-loop
    # variable, which Lua 5.4+ rejects), so load only the helper
    source = UTILS_LUA.read_text()
    lua.execute(source[source.index("storage.utils.note_dropped_direction") :])
    make = lua.eval(
        """function(name, type, direction, fluidboxes)
            local fb = {}
            for i = 1, fluidboxes do fb[i] = {} end
            return {name = name, type = type, direction = direction, valid = true,
                    prototype = {fluidbox_prototypes = fb}}
        end"""
    )
    run = lua.eval(
        """function(entity, requested)
            local out = storage.utils.note_dropped_direction(
                {warnings = {"'not connected to power network'"}}, entity, requested)
            return out.warnings
        end"""
    )
    return lambda *entity: list(run(make(*entity[:-1]), entity[-1]).values())


def test_assembler_2_facing_north_is_reported(note):
    warnings = note("assembling-machine-2", "assembling-machine", 0, 2, EAST)
    assert warnings[0] == "'not connected to power network'"
    assert warnings[1] == (
        '"assembling-machine-2 was placed facing north: '
        'it takes a direction only while its recipe uses a fluid"'
    )


def test_assembler_1_facing_north_is_reported(note):
    warnings = note("assembling-machine-1", "assembling-machine", 0, 0, EAST)
    assert "no fluid connections" in warnings[1]


def test_kept_direction_adds_nothing(note):
    assert len(note("chemical-plant", "assembling-machine", EAST, 4, EAST)) == 1
    assert len(note("assembling-machine-2", "assembling-machine", 0, 2, 0)) == 1


def test_other_entities_are_untouched(note):
    assert len(note("boiler", "boiler", 0, 2, EAST)) == 1
