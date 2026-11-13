"""get_resource_patch on crude oil reports the field, in crude oil per second. Server-free (Lua via lupa).

Factorio 2.0: crude-oil normal_resource_amount = 300000 (100% yield), product
10 crude oil per mining cycle of 1 s, pumpjack mining_speed = 1. Well positions
are from a 2.0.73 map: one field of three wells up to 14 tiles apart, and a
single well far away.
"""

import math
from pathlib import Path

import pytest

from fle.env.entities import BoundingBox, Position, ResourcePatch

lupa = pytest.importorskip("lupa")

PATCH_LUA = (
    Path(__file__).resolve().parents[2]
    / "fle/env/tools/agent/get_resource_patch/server.lua"
)

WELLS = [
    (175.5, 826.5, 300000),
    (183.5, 819.5, 450000),
    (193.5, 829.5, 60000),
    (-387.5, 381.5, 300000),
]


def _lua():
    lua = lupa.LuaRuntime()
    lua.execute(
        """
        rendering = {clear = function() end, draw_circle = function() end}
        prototypes = {entity = {
            ["crude-oil"] = {infinite_resource = true, normal_resource_amount = 300000,
                mineable_properties = {mining_time = 1,
                    products = {{type = "fluid", name = "crude-oil", amount = 10}}}},
            ["pumpjack"] = {mining_speed = 1},
        }}
        wells = {}
        surface = {}
        function surface.find_entities_filtered(f)
            local out = {}
            for _, w in ipairs(wells) do
                local dx, dy = w.position.x - f.position.x, w.position.y - f.position.y
                if math.sqrt(dx * dx + dy * dy) <= f.radius then out[#out + 1] = w end
            end
            return out
        end
        storage = {actions = {}, agent_characters = {{surface = surface}}}
        """
    )
    add = lua.eval(
        "function(x, y, a) wells[#wells + 1] = {position = {x = x, y = y}, amount = a} end"
    )
    for well in WELLS:
        add(*well)
    lua.execute(PATCH_LUA.read_text())
    return lua


def test_field_joins_wells_and_reports_per_second():
    lua = _lua()
    result = lua.eval(
        'storage.actions.get_resource_patch(1, "crude-oil", 183.5, 819.5, 30)'
    )
    assert result.wells == 3
    # 10/s at 100%: 10 + 15 + 2
    assert math.isclose(result.size, 27)
    assert result.bounding_box.left_top.x == 175.5
    assert result.bounding_box.right_bottom.y == 829.5


def test_single_well_field():
    lua = _lua()
    result = lua.eval(
        'storage.actions.get_resource_patch(1, "crude-oil", -387.5, 381.5, 30)'
    )
    assert result.wells == 1
    assert math.isclose(result.size, 10)


def test_no_resource_in_radius_is_not_found_not_an_error():
    # the client turns {not_found = true} into None (documented: "ResourcePatch if found, else None")
    lua = _lua()
    result = lua.eval(
        'storage.actions.get_resource_patch(1, "crude-oil", 0.5, 0.5, 30)'
    )
    assert result.not_found is True


def test_resource_patch_takes_a_rate_and_well_count():
    box = BoundingBox(
        left_top=Position(x=0, y=0),
        right_bottom=Position(x=1, y=1),
        left_bottom=Position(x=0, y=1),
        right_top=Position(x=1, y=0),
    )
    patch = ResourcePatch(name="crude-oil", size=12.5, bounding_box=box, wells=2)
    assert patch.size == 12.5 and patch.wells == 2
    ore = ResourcePatch(name="iron-ore", size=1200, bounding_box=box)
    assert ore.size == 1200 and isinstance(ore.size, int) and ore.wells is None
