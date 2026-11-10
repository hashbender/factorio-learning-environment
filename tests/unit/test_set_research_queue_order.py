"""set_research makes the requested technology the current research when others are queued. Server-free.

Runs the tool's server.lua in lupa against a fake force with a research queue.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SERVER_LUA = (
    Path(__file__).resolve().parents[2] / "fle/env/tools/agent/set_research/server.lua"
).read_text()

# LuaForce: research_queue lists LuaTechnology objects, current research first; assigning
# it takes technology names. cancel_current_research() drops the head, add_research() appends.
FAKE_FORCE = """
local techs = {}
local function tech(name)
    techs[name] = {name = name, researched = false, enabled = true, prerequisites = {},
                   research_unit_count = 10,
                   research_unit_ingredients = {{name = "automation-science-pack", amount = 1, type = "item"}}}
end
for _, n in ipairs({"automation", "logistics", "electronics", "military"}) do tech(n) end
local queue = {}
local force = {technologies = techs}
function force.cancel_current_research() table.remove(queue, 1) end
function force.add_research(name) queue[#queue + 1] = name; return true end
function force.queue_names() return table.concat(queue, ",") end
local function as_techs()
    local o = {}
    for _, n in ipairs(queue) do o[#o + 1] = techs[n] end
    return o
end
setmetatable(force, {
    __index = function(_, k)
        if k == "research_queue" then return as_techs() end
        if k == "current_research" then return techs[queue[1]] end
    end,
    __newindex = function(_, k, v)
        assert(k == "research_queue")
        queue = {}
        for _, n in ipairs(v) do queue[#queue + 1] = n end
    end,
})
storage = {actions = {}, agent_characters = {[1] = {force = force}}}
return force
"""


@pytest.fixture()
def force():
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    force = runtime.execute(FAKE_FORCE)
    runtime.execute(SERVER_LUA)
    force.research_queue = runtime.table("automation", "logistics", "electronics")
    return runtime, force


def test_requested_technology_becomes_current(force):
    runtime, f = force
    runtime.globals().storage.actions.set_research(1, "military")
    assert f.queue_names() == "military,logistics,electronics"
    assert f.current_research.name == "military"


def test_queued_technology_moves_to_the_front(force):
    runtime, f = force
    runtime.globals().storage.actions.set_research(1, "electronics")
    assert f.queue_names() == "electronics,logistics"


def test_empty_queue(force):
    runtime, f = force
    f.research_queue = runtime.table()
    ingredients = runtime.globals().storage.actions.set_research(1, "automation")
    assert f.queue_names() == "automation"
    assert ingredients[1]["count"] == 10
