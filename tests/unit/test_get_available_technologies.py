"""get_available_technologies lists what the technology screen shows as researchable. Server-free.

Runs the tool's server.lua in lupa against a fake force (2.0 shapes: research_unit_energy in
ticks, research_trigger on the prototype), then the client on a stubbed RCON call.
"""

from pathlib import Path

import pytest

from fle.env.tools.agent.get_available_technologies.client import (
    GetAvailableTechnologies,
)

lupa = pytest.importorskip("lupa")

TOOLS = Path(__file__).resolve().parents[2] / "fle/env/tools/agent"
SERVER_LUA = (TOOLS / "get_available_technologies/server.lua").read_text()

FAKE_FORCE = """
local techs = {}
local function tech(name, prerequisites, fields)
    local t = {name = name, researched = false, enabled = true, prerequisites = {},
               research_unit_count = 10, research_unit_energy = 600,
               research_unit_ingredients = {{name = "automation-science-pack", amount = 1, type = "item"}},
               prototype = {}}
    for _, p in ipairs(prerequisites or {}) do t.prerequisites[p] = techs[p] end
    for k, v in pairs(fields or {}) do t[k] = v end
    techs[name] = t
end
tech("automation", nil, {researched = true})
tech("logistics")
tech("electronics", {"automation"}, {research_unit_count = 30, research_unit_energy = 900})
tech("automation-2", {"electronics"})
tech("logistic-science-pack", {"automation"}, {research_unit_count = 75,
    research_unit_ingredients = {{name = "automation-science-pack", amount = 1, type = "item"},
                                 {name = "logistic-science-pack", amount = 1, type = "item"}}})
tech("disabled", nil, {enabled = false})
tech("steam-power", nil, {research_unit_count = 0, research_unit_ingredients = {},
    prototype = {research_trigger = {type = "craft-item", item = {name = "iron-plate"}, count = 50}}})
storage = {actions = {}, agent_characters = {[1] = {force = {technologies = techs}}}}
"""


def _run():
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(FAKE_FORCE)
    runtime.execute(SERVER_LUA)
    ok, result = runtime.eval(
        "function() return pcall(storage.actions.get_available_technologies, 1) end"
    )()
    assert ok, result

    def py(v):
        if lupa.lua_type(v) == "table":
            return {k: py(x) for k, x in v.items()}
        return v

    return py(result)


def _client(response):
    tool = object.__new__(GetAvailableTechnologies)
    tool.player_index = 1
    tool.execute = lambda *a: (response, 0)
    return tool()


def test_lists_only_researchable_now():
    techs = _client(_run())
    assert [t.name for t in techs] == [
        "electronics",
        "logistic-science-pack",
        "logistics",
        "steam-power",
    ]


def test_units_ingredients_and_time():
    techs = {t.name: t for t in _client(_run())}
    electronics = techs["electronics"]
    assert (electronics.unit_count, electronics.unit_time) == (30, 15.0)
    assert [(i.name, i.count) for i in electronics.ingredients] == [
        ("automation-science-pack", 1)
    ]
    assert [(i.name, i.count) for i in techs["logistic-science-pack"].ingredients] == [
        ("automation-science-pack", 1),
        ("logistic-science-pack", 1),
    ]
    assert electronics.trigger is None


def test_trigger_technology():
    steam = {t.name: t for t in _client(_run())}["steam-power"]
    assert steam.trigger == "craft 50 iron-plate"
    assert (steam.unit_count, steam.ingredients) == (0, [])


def test_nothing_available():
    assert _client({}) == []


def test_trigger_description_matches_set_research():
    def fn(src):
        i = src.index("local function trigger_description")
        return src[i : src.index("\nend\n", i)]

    assert fn(SERVER_LUA) == fn((TOOLS / "set_research/server.lua").read_text())
