"""set_research refuses Factorio 2.0 trigger technologies with the trigger named. Server-free.

Runs the tool's server.lua in lupa against a fake force.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SERVER_LUA = (
    Path(__file__).resolve().parents[2] / "fle/env/tools/agent/set_research/server.lua"
).read_text()

FAKE_FORCE = """
local function tech(name, fields)
    local t = {name = name, researched = false, enabled = true, prerequisites = {},
               research_unit_count = 10,
               research_unit_ingredients = {{name = "automation-science-pack", amount = 1, type = "item"}},
               prototype = {}}
    for k, v in pairs(fields or {}) do t[k] = v end
    return t
end
local done = tech("done", {researched = true})
local force = {technologies = {}, research_queue = {}, cancelled = 0, added = {}}
force.technologies["steam-power"] = tech("steam-power",
    {prototype = {research_trigger = {type = "craft-item", item = {name = "iron-plate"}, count = 50}}})
force.technologies["oil-processing"] = tech("oil-processing",
    {prerequisites = {["fluid-handling"] = tech("fluid-handling")},
     prototype = {research_trigger = {type = "mine-entity", entity = "crude-oil"}}})
force.technologies["automation-science-pack"] = tech("automation-science-pack",
    {prototype = {research_trigger = {type = "craft-item", item = "lab", count = 1}}})
force.technologies["space-science-pack"] = tech("space-science-pack",
    {prototype = {research_trigger = {type = "send-item-to-orbit", item = {name = "satellite"}}}})
force.technologies["automation"] = tech("automation", {prerequisites = {done = done}})
function force.cancel_current_research() force.cancelled = force.cancelled + 1 end
function force.add_research(name)
    force.added[#force.added + 1] = name
    return force.technologies[name].prototype.research_trigger == nil
end
storage = {actions = {}, agent_characters = {[1] = {force = force}}}
return force
"""


@pytest.fixture()
def lua():
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    force = runtime.execute(FAKE_FORCE)
    runtime.execute(SERVER_LUA)
    return runtime, force


def _set_research(lua, name):
    runtime, _ = lua
    ok, result = runtime.eval(
        "function(n) return pcall(storage.actions.set_research, 1, n) end"
    )(name)
    return ok, result


@pytest.mark.parametrize(
    "name, trigger",
    [
        ("steam-power", "craft 50 iron-plate"),
        ("automation-science-pack", "craft lab"),
        ("space-science-pack", "send satellite to orbit"),
    ],
)
def test_trigger_technology_is_refused_with_its_trigger(lua, name, trigger):
    ok, message = _set_research(lua, name)
    assert not ok
    assert message.endswith(
        f'"Cannot start research for {name}. It is a trigger technology, '
        f'completed by a game action instead of labs: {trigger}"'
    )


def test_trigger_refusal_lists_missing_prerequisites(lua):
    ok, message = _set_research(lua, "oil-processing")
    assert not ok
    assert message.endswith(
        ': mine crude-oil. Missing prerequisites: fluid-handling"',
    )


def test_trigger_refusal_keeps_current_research(lua):
    _, force = lua
    _set_research(lua, "steam-power")
    assert force.cancelled == 0
    assert len(list(force.added.values())) == 0


def test_lab_technology_is_still_set(lua):
    _, force = lua
    ok, ingredients = _set_research(lua, "automation")
    assert ok
    assert ingredients[1]["count"] == 10
    assert list(force.added.values()) == ["automation"]
