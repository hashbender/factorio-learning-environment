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
-- As on a 2.0.73 server: add_research() refuses (returns false) a technology that is already queued
function force.cancel_current_research() table.remove(queue, 1) end
function force.add_research(name)
    for _, n in ipairs(queue) do if n == name then return false end end
    queue[#queue + 1] = name; return true
end
-- names the game drops from an assigned queue (stands in for any refusal)
refused = {}
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
        for _, n in ipairs(v) do if not refused[n] then queue[#queue + 1] = n end end
    end,
})
storage = {actions = {}, agent_characters = {[1] = {force = force}}}
tech("automobilism")
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


def test_queued_technology_that_is_not_current(force):
    # Regression: cancel_current_research() dropped the head, then add_research() refused the
    # already-queued technology: the call raised "Failed to start research" with the queue changed.
    runtime, f = force
    f.research_queue = runtime.table(
        "automation", "logistics", "automobilism", "electronics"
    )
    runtime.globals().storage.actions.set_research(1, "automobilism")
    assert f.queue_names() == "automobilism,logistics,electronics"


def test_current_technology_keeps_the_queue(force):
    runtime, f = force
    runtime.globals().storage.actions.set_research(1, "automation")
    assert f.queue_names() == "automation,logistics,electronics"


def test_a_failed_call_leaves_the_queue_unchanged(force):
    runtime, f = force
    runtime.globals().refused["military"] = True
    with pytest.raises(
        lupa.LuaError,
        match="Failed to start research for military; the research queue is unchanged",
    ):
        runtime.globals().storage.actions.set_research(1, "military")
    assert f.queue_names() == "automation,logistics,electronics"


def test_a_refused_call_leaves_the_queue_unchanged(force):
    runtime, f = force
    with pytest.raises(lupa.LuaError, match="does not exist"):
        runtime.globals().storage.actions.set_research(1, "no-such-tech")
    assert f.queue_names() == "automation,logistics,electronics"
