"""Assembling-machine fluid ports come from the game. Server-free.

serialize.lua's read_assembler_fluid_ports runs in lupa against a fake LuaFluidBox. The
fake's pipe connections are those of a Factorio 2.0.73 assembling-machine-2 facing north at
(0.5, 0.5) with a fluid recipe: the input box's port tile is (0.5, -0.5) and a pipe must be
at (0.5, -1.5); the output box opens south onto (0.5, 2.5). With no fluid recipe the game
reports no pipe connections.
"""

from pathlib import Path

import pytest

from fle.env import AdvancedAssemblingMachine, IndexedPosition, Position
from fle.env.tools.agent.connect_entities.resolvers.fluid_connection_resolver import (
    FluidConnectionResolver,
)

lupa = pytest.importorskip("lupa")

SERIALIZE_LUA = (
    Path(__file__).resolve().parents[2] / "fle/env/mods/serialize.lua"
).read_text()

FAKE = """
local boxes = ...
local fluidbox = setmetatable({}, {__len = function() return #boxes end})
function fluidbox.get_prototype(i) return {boxes[i].proto} end
function fluidbox.get_pipe_connections(i) return boxes[i].connections end
function fluidbox.get_filter(i) return boxes[i].filter end
return fluidbox
"""


def _read(boxes_lua: str, recipe_lua: str = "nil"):
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    start = SERIALIZE_LUA.index("local function read_assembler_fluid_ports")
    end = SERIALIZE_LUA.index("-- Helper function to check if a position is valid")
    read = lua.execute(SERIALIZE_LUA[start:end] + "\nreturn read_assembler_fluid_ports")
    fluidbox = lua.execute(FAKE, lua.eval(boxes_lua))
    entity = lua.eval(
        "function(fb, recipe) return {fluidbox = fb, get_recipe = function() return recipe end} end"
    )(fluidbox, lua.eval(recipe_lua))
    ports = read(entity)

    def points(t):
        return [
            (t[i].x, t[i].y, None if t[i].type is None else t[i].type.strip('"'))
            for i in range(1, len(t) + 1)
        ]

    return points(ports.all), points(ports.inputs), points(ports.outputs)


INPUT_BOX = (
    "{proto = {production_type = 'input'}, connections = {"
    "{flow_direction = 'input', connection_type = 'normal',"
    " position = {x = 0.5, y = -0.5}, target_position = {x = 0.5, y = -1.5}}}}"
)
OUTPUT_BOX = (
    "{proto = {production_type = 'output'}, connections = {"
    "{flow_direction = 'output', connection_type = 'normal',"
    " position = {x = 0.5, y = 1.5}, target_position = {x = 0.5, y = 2.5}}}}"
)


def test_input_and_output_ports_from_the_game():
    recipe = (
        "{ingredients = {{type = 'item', name = 'barrel'}, {type = 'fluid', name = 'water'}},"
        " products = {{type = 'item', name = 'water-barrel'}}}"
    )
    all_, inputs, outputs = _read(f"{{{INPUT_BOX}, {OUTPUT_BOX}}}", recipe)
    assert all_ == [(0.5, -1.5, None), (0.5, 2.5, None)]
    assert inputs == [(0.5, -1.5, "water")]
    assert outputs == [(0.5, 2.5, "")]


def test_filter_names_the_fluid():
    box = INPUT_BOX.replace("connections", "filter = {name = 'lubricant'}, connections")
    _, inputs, _ = _read(f"{{{box}}}")
    assert inputs == [(0.5, -1.5, "lubricant")]


def test_no_fluid_recipe_no_ports():
    boxes = "{{proto = {production_type = 'input'}, connections = {}}, {proto = {production_type = 'output'}, connections = {}}}"
    assert _read(boxes) == ([], [], [])


def test_no_fluid_boxes():
    assert _read("{}") == ([], [], [])


def _assembler(inputs, outputs):
    return AdvancedAssemblingMachine.model_construct(
        name="assembling-machine-2",
        position=Position(x=0.5, y=0.5),
        connection_points=[Position(x=p[0], y=p[1]) for p in inputs + outputs],
        input_connection_points=[
            IndexedPosition(x=x, y=y, type=t) for x, y, t in inputs
        ],
        output_connection_points=[
            IndexedPosition(x=x, y=y, type=t) for x, y, t in outputs
        ],
        fluid_box=[],
    )


def test_resolver_pipes_into_the_input_port_only():
    resolver = object.__new__(FluidConnectionResolver)
    machine = _assembler([(0.5, -1.5, "water")], [(0.5, 2.5, "")])
    targets = resolver.get_target_fluid_positions(machine)
    assert [(p.x, p.y, p.type) for p in targets] == [(0.5, -1.5, "")]


def test_resolver_takes_fluid_from_the_output_port_only():
    resolver = object.__new__(FluidConnectionResolver)
    machine = _assembler([(0.5, -1.5, "water-barrel")], [(0.5, 2.5, "water")])
    sources = resolver.get_source_fluid_positions(machine)
    assert [(p.x, p.y, p.type) for p in sources] == [(0.5, 2.5, "water")]


def test_resolver_without_typed_ports_uses_connection_points():
    resolver = object.__new__(FluidConnectionResolver)
    machine = _assembler([], [])
    machine.connection_points = [Position(x=0.5, y=-1.5)]
    targets = resolver.get_target_fluid_positions(machine)
    assert [(p.x, p.y) for p in targets] == [(0.5, -1.5)]
