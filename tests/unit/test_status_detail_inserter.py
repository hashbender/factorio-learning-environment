"""status_detail for an inserter waiting for source items while its pickup belt holds items:
the drop target is not taking those items now (no server; serialize.lua in lupa)."""

from pathlib import Path

import pytest

from tests.unit.test_status_detail import STUB_LUA

SERIALIZE_LUA = Path(__file__).resolve().parents[2] / "fle/env/mods/serialize.lua"

HELPERS = """
function belt(lane1, lane2)
    return {valid = true, type = "transport-belt", name = "transport-belt", position = {x = -24.5, y = 28.5},
        get_max_transport_line_index = function() return 2 end,
        get_transport_line = function(i) if i == 1 then return {items = lane1} end return {items = lane2} end}
end
function lab(items, tech)
    return {valid = true, type = "lab", name = "lab", position = {x = -23.5, y = 31.5},
        get_inventory = function() return inv(items) end, force = {current_research = tech}}
end
function machine(items, recipe)
    return {valid = true, type = "assembling-machine", name = "assembling-machine-1", position = {x = 3.5, y = 3.5},
        get_recipe = function() return recipe end, get_inventory = function() return inv(items) end}
end
function inserter(pickup, drop)
    return {status = 17, pickup_position = {x = -24.5, y = 28.5}, pickup_target = pickup, drop_target = drop}
end
RED_GREEN = {name = "circuit-network", research_unit_ingredients = {
    {name = "automation-science-pack", amount = 1}, {name = "logistic-science-pack", amount = 1}}}
CIRCUIT = {name = "electronic-circuit", ingredients = {
    {type = "item", name = "iron-plate", amount = 1}, {type = "item", name = "copper-cable", amount = 3}}}
"""


@pytest.fixture(scope="module")
def lua():
    lupa = pytest.importorskip("lupa")
    rt = lupa.LuaRuntime()
    rt.execute(STUB_LUA)
    rt.execute(SERIALIZE_LUA.read_text())
    rt.execute(HELPERS)
    return rt


def detail(lua, src):
    return lua.eval(f"storage.utils.status_detail({src})")


BASE = "waiting for items from transport-belt at (-24.5, 28.5)"


def test_lab_buffer_holds_the_pack_on_the_belt(lua):
    # fmg-world-12, tick 5197277: lab working on circuit-network, holds red 4 + green 1
    src = """inserter(belt({}, {["automation-science-pack"] = 3}),
        lab({["automation-science-pack"] = 4, ["logistic-science-pack"] = 1}, RED_GREEN))"""
    assert detail(lua, src) == (
        BASE + "; belt has automation-science-pack 3, not taken now by lab at (-23.5, 31.5)"
        " (holds automation-science-pack 4)"
    )


def test_lab_also_names_missing_packs(lua):
    src = """inserter(belt({["automation-science-pack"] = 2}, {["automation-science-pack"] = 5}),
        lab({["automation-science-pack"] = 6}, RED_GREEN))"""
    assert detail(lua, src) == (
        BASE + "; belt has automation-science-pack 7, not taken now by lab at (-23.5, 31.5)"
        " (holds automation-science-pack 6; missing logistic-science-pack (0 of 1))"
    )


def test_lab_pack_not_used_by_the_research(lua):
    src = """inserter(belt({["military-science-pack"] = 4}, {}),
        lab({["automation-science-pack"] = 1, ["logistic-science-pack"] = 1}, RED_GREEN))"""
    assert detail(lua, src) == (
        BASE + "; belt has military-science-pack 4, not taken now by lab at (-23.5, 31.5)"
        " (military-science-pack not used by circuit-network)"
    )


def test_lab_without_research(lua):
    src = """inserter(belt({["automation-science-pack"] = 1}, {}), lab({}, nil))"""
    assert detail(lua, src) == (
        BASE + "; belt has automation-science-pack 1, not taken now by lab at (-23.5, 31.5)"
        " (holds automation-science-pack 0; no research set)"
    )


def test_assembler_one_buffer_full_another_missing(lua):
    src = """inserter(belt({["iron-plate"] = 4}, {["iron-plate"] = 4}),
        machine({["iron-plate"] = 10}, CIRCUIT))"""
    assert detail(lua, src) == (
        BASE + "; belt has iron-plate 8, not taken now by assembling-machine-1 at (3.5, 3.5)"
        " (holds iron-plate 10; missing copper-cable (0 of 3 per craft))"
    )


def test_assembler_item_not_in_recipe(lua):
    src = """inserter(belt({["coal"] = 3}, {}), machine({}, CIRCUIT))"""
    assert detail(lua, src) == (
        BASE + "; belt has coal 3, not taken now by assembling-machine-1 at (3.5, 3.5)"
        " (coal not in recipe electronic-circuit; missing iron-plate (0 of 1 per craft),"
        " copper-cable (0 of 3 per craft))"
    )


def test_empty_belt_or_other_targets_keep_the_plain_text(lua):
    assert detail(lua, "inserter(belt({}, {}), lab({}, RED_GREEN))") == BASE
    chest = '{valid = true, type = "container", name = "iron-chest", position = {x = 0.5, y = 0.5}}'
    assert detail(lua, f"inserter(belt({{coal = 2}}, {{}}), {chest})") == BASE
    assert detail(lua, "inserter(belt({coal = 2}, {}), nil)") == BASE


def test_a_failing_accessor_keeps_the_plain_text(lua):
    src = """inserter(belt({coal = 2}, {}), setmetatable({valid = true, type = "lab", name = "lab",
        position = {x = 0, y = 0}}, {__index = function() error('x') end}))"""
    assert detail(lua, src) == BASE
