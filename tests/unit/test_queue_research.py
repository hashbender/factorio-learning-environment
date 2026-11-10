"""queue_research appends technologies to the research queue. Server-free.

The server tests run the tool's server.lua in lupa against a fake force; the client
tests stub the RCON call.
"""

from pathlib import Path

import pytest

from fle.env.game_types import Technology
from fle.env.tools.agent.queue_research.client import QueueResearch

lupa = pytest.importorskip("lupa")

SERVER_LUA = (
    Path(__file__).resolve().parents[2]
    / "fle/env/tools/agent/queue_research/server.lua"
).read_text()

# LuaForce: research_queue lists LuaTechnology objects, current research first; assigning
# it takes technology names. add_research() appends when every prerequisite is researched
# or queued and the queue has room, else returns false.
FAKE_FORCE = """
local techs = {}
local function tech(name, prerequisites, fields)
    local t = {name = name, researched = false, enabled = true, prerequisites = {}, prototype = {}}
    for _, p in ipairs(prerequisites or {}) do t.prerequisites[p] = techs[p] end
    for k, v in pairs(fields or {}) do t[k] = v end
    techs[name] = t
end
tech("automation")
tech("logistics")
tech("automation-2", {"automation"})
tech("logistics-2", {"logistics", "automation-2"})
tech("military", nil, {researched = true})
tech("disabled", nil, {enabled = false})
tech("oil-processing", nil, {prototype = {research_trigger = {type = "mine-entity", entity = "crude-oil"}}})
for i = 1, 7 do tech("filler-" .. i) end
local queue = {}
local force = {technologies = techs}
function force.add_research(name)
    if #queue >= 7 then return false end
    for _, n in ipairs(queue) do if n == name then return false end end
    local inq = {}
    for _, n in ipairs(queue) do inq[n] = true end
    for p, t in pairs(techs[name].prerequisites) do
        if not t.researched and not inq[p] then return false end
    end
    queue[#queue + 1] = name
    return true
end
function force.queue_names() return table.concat(queue, ",") end
setmetatable(force, {
    __index = function(_, k)
        if k == "research_queue" then
            local o = {}
            for _, n in ipairs(queue) do o[#o + 1] = techs[n] end
            return o
        end
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
def lua():
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    force = runtime.execute(FAKE_FORCE)
    runtime.execute(SERVER_LUA)
    call = runtime.eval(
        "function(names) return pcall(storage.actions.queue_research, 1, names) end"
    )

    def queue(*names):
        ok, result = call(runtime.table(*names))
        if not ok:
            return False, result
        return True, [result[i] for i in range(1, len(result) + 1)]

    return queue, force


def test_appends_in_order(lua):
    queue, force = lua
    ok, result = queue("automation", "automation-2")
    assert ok
    assert result == ['"automation"', '"automation-2"']
    assert force.queue_names() == "automation,automation-2"


def test_prerequisite_earlier_in_the_same_call(lua):
    queue, force = lua
    ok, _ = queue("logistics", "automation", "automation-2", "logistics-2")
    assert ok
    assert force.queue_names() == "logistics,automation,automation-2,logistics-2"


def test_already_queued_keeps_its_place(lua):
    queue, force = lua
    queue("automation", "logistics")
    ok, _ = queue("automation", "automation-2")
    assert ok
    assert force.queue_names() == "automation,logistics,automation-2"


def test_empty_list_returns_the_queue(lua):
    queue, _ = lua
    queue("automation")
    assert queue() == (True, ['"automation"'])


def test_missing_prerequisite_queues_nothing(lua):
    queue, force = lua
    queue("logistics")
    ok, message = queue("automation", "logistics-2")
    assert not ok
    assert message.endswith(
        '"Cannot queue logistics-2. Missing prerequisites (not researched or queued): automation-2"'
    )
    assert force.queue_names() == "logistics"


def test_full_queue(lua):
    queue, force = lua
    queue(*[f"filler-{i}" for i in range(1, 8)])
    ok, message = queue("automation")
    assert not ok
    assert message.endswith(
        '"Cannot queue automation. The research queue is full (7 technologies)"'
    )


@pytest.mark.parametrize(
    "name, expected",
    [
        ("nope", "Technology nope does not exist"),
        ("military", "Technology military is already researched"),
        ("disabled", "Technology disabled is not enabled"),
        (
            "oil-processing",
            "Cannot queue oil-processing. It is a trigger technology, "
            "completed by a game action instead of labs: mine crude-oil",
        ),
    ],
)
def test_refused_before_anything_is_queued(lua, name, expected):
    queue, force = lua
    ok, message = queue("automation", name)
    assert not ok
    assert message.endswith(f'"{expected}"')
    assert force.queue_names() == ""


def _tool(reply):
    tool = QueueResearch.__new__(QueueResearch)
    tool.player_index = 1
    calls = []

    def execute(*args):
        calls.append(args)
        return reply, 0

    tool.execute = execute
    return tool, calls


def test_client_accepts_members_names_and_a_single_technology():
    tool, calls = _tool(["automation", "automation-2"])
    assert tool([Technology.Automation, "automation-2"]) == [
        "automation",
        "automation-2",
    ]
    assert calls[-1] == (1, ["automation", "automation-2"])
    tool(Technology.Logistics)
    assert calls[-1] == (1, ["logistics"])


def test_client_empty_queue():
    tool, _ = _tool({})
    assert tool([]) == []


def test_client_error_keeps_the_whole_message():
    reply = (
        '[string "-- Describes a Factorio 2.0 research trigger..."]:60: '
        '"Cannot queue oil-processing. It is a trigger technology, completed by a game '
        'action instead of labs: mine crude-oil"'
    )
    tool, _ = _tool(reply)
    with pytest.raises(Exception) as exc_info:
        tool(Technology.OilProcessing)
    assert str(exc_info.value) == (
        "Cannot queue oil-processing. It is a trigger technology, completed by a game "
        "action instead of labs: mine crude-oil"
    )


def test_client_unknown_name_lists_closest_names():
    tool, _ = _tool('[string "..."]:52: "Technology research-speed does not exist"')
    with pytest.raises(Exception) as exc_info:
        tool(["automation", "research-speed"])
    assert str(exc_info.value).startswith(
        "Technology research-speed does not exist. Closest technology names: "
        "research-speed-1, research-speed-2"
    )
