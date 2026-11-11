"""connect_entities with electric poles: a near-straight line of poles at full wire
reach, bending only round tiles where a pole cannot be built. Server-free (lupa,
fake surface).

Before, the poles followed the game's walking path (which goes round cliffs and
lakes) and were placed every 4 path points with a small pole reach of 4: on a
350-tile route a gpt agent was asked for 147 small poles, 2-3 tiles apart, where
about 50 do.
"""

import math
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

SERVER_LUA = (
    Path(__file__).resolve().parents[2]
    / "fle/env/tools/agent/connect_entities/server.lua"
).read_text()

FAKE = """
local state = ...
local function key(p) return p.x .. "," .. p.y end
local surface = {}
function surface.can_place_entity(args)
    local p = args.position
    if state.blocked[key(p)] then return false end
    for _, e in pairs(state.built) do
        if e.position.x == p.x and e.position.y == p.y then return false end
    end
    return true
end
function surface.find_entities_filtered(args)
    local out = {}
    for _, e in pairs(state.poles) do
        local p = args.position
        if p and args.radius and math.abs(e.position.x - p.x) <= args.radius
            and math.abs(e.position.y - p.y) <= args.radius then
            out[#out + 1] = e
        end
    end
    return out
end
function surface.find_entity(name, p) return nil end
function surface.get_tile(x, y) return {name = "grass-1"} end
function surface.find_non_colliding_position(_, p) return p end
function surface.create_entity(args)
    local e = {name = args.name, valid = true, position = {x = args.position.x, y = args.position.y},
               electric_network_id = 7, type = "electric-pole"}
    state.built[#state.built + 1] = e
    return e
end
game = {surfaces = {[1] = surface}, tick = 0}
defines = {inventory = {character_main = 1}, direction = {north = 0}}
rendering = {draw_circle = function() end, draw_line = function() end}
local player = {valid = true, position = {x = 0, y = 0}, surface = surface, force = "player"}
function player.teleport(p) state.teleports[#state.teleports + 1] = {x = p.x or p[1], y = p.y or p[2]}
    player.position = {x = p.x or p[1], y = p.y or p[2]} end
function player.get_inventory(_)
    return {get_item_count = function(name) return state.inv[name] or 0 end}
end
function player.remove_item(stack) state.inv[stack.name] = (state.inv[stack.name] or 0) - stack.count end
storage = {
    actions = {}, paths = {}, elapsed_ticks = 0, agent_characters = {[1] = player},
    utils = {
        get_closest_entity = function() return nil end,
        calculate_movement_ticks = function() return 0 end,
        get_entity_direction = function(_, d) return d end,
        serialize_entity = function(e) return {name = e.name, position = e.position} end,
        get_direction = function(a, b) return 0 end,
    },
}
"""


def _lua(blocked=(), poles=(), items=None):
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    state = lua.eval("{}")
    state.blocked = lua.table_from({f"{x},{y}": True for x, y in blocked})
    state.poles = lua.table_from(
        [
            lua.table_from(
                {
                    "name": name,
                    "valid": True,
                    "type": "electric-pole",
                    "electric_network_id": 1,
                    "position": lua.table_from({"x": x, "y": y}),
                }
            )
            for name, x, y in poles
        ]
    )
    state.built = lua.table_from([])
    state.teleports = lua.table_from([])
    state.inv = lua.table_from(items or {})
    lua.execute(FAKE, state)
    lua.execute(SERVER_LUA)
    return lua, state


def _plan(
    lua,
    start,
    goal,
    reach=7.5,
    offset=0.5,
    blocked=lambda x, y: False,
    start_reach=7.5,
    goal_reach=None,
    guide=None,
):
    opts = {
        "start": lua.table_from({"x": start[0], "y": start[1]}),
        "goal": lua.table_from({"x": goal[0], "y": goal[1]}),
        "reach": reach,
        "offset": offset,
        "free": lambda p: not blocked(p.x, p.y),
    }
    if start_reach:
        opts["start_reach"] = start_reach
    if goal_reach:
        opts["goal_reach"] = goal_reach
    if guide:
        opts["guide"] = lua.table_from(
            [lua.table_from({"x": x, "y": y}) for x, y in guide]
        )
    res = lua.eval("storage.utils.plan_pole_line")(lua.table_from(opts))
    plan, why = res if isinstance(res, tuple) else (res, None)
    if plan is None:
        return None, why
    return [(plan[i].x, plan[i].y) for i in range(1, len(plan) + 1)], None


def _off_line(p, a, b):
    (x, y), (ax, ay), (bx, by) = p, a, b
    return abs((bx - ax) * (ay - y) - (ax - x) * (by - ay)) / math.hypot(bx - ax, by - ay)


def _spans(start, poles):
    pts = [start] + poles
    return [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def test_100_tiles_open_ground_about_14_small_poles():
    lua, _ = _lua()
    start, goal = (0.5, 0.5), (100.5, 0.5)
    poles, why = _plan(lua, start, goal)
    assert why is None
    assert 14 <= len(poles) <= 15, poles
    assert all(y == 0.5 for _, y in poles), "a straight line on open ground"
    assert max(_spans(start, poles)) <= 7.5
    assert min(_spans(start, poles)[:-1]) >= 7, "each pole at (nearly) full reach"
    assert poles[-1] == goal


def test_the_350_tile_oil_route_needs_about_50_not_147():
    """The live route: pole at (-34.5, -70.5) to a pumpjack at (-280.5, -313.5)."""
    lua, _ = _lua()
    start, goal = (-34.5, -70.5), (-278.5, -311.5)
    poles, why = _plan(lua, start, goal)
    assert why is None
    straight = math.dist(start, goal)
    assert len(poles) <= math.ceil(straight / 7.0) + 1, len(poles)
    assert 45 <= len(poles) <= 52
    assert max(_off_line(p, start, goal) for p in poles) <= 1.5, "near-straight"
    assert max(_spans(start, poles)) <= 7.5


def test_a_blocked_tile_on_the_line_moves_one_pole_aside():
    lua, _ = _lua()
    start, goal = (0.5, 0.5), (50.5, 0.5)
    blocked = {(7.5, 0.5), (14.5, 0.5), (13.5, 0.5)}
    poles, why = _plan(lua, start, goal, blocked=lambda x, y: (x, y) in blocked)
    assert why is None
    assert not set(poles) & blocked
    assert max(_spans(start, poles)) <= 7.5
    assert len(poles) <= 9
    assert max(abs(y - 0.5) for _, y in poles) <= 2


def test_a_band_of_trees_narrower_than_the_reach_is_spanned_by_the_wires():
    lua, _ = _lua()
    start, goal = (0.5, 0.5), (60.5, 0.5)

    def blocked(x, y):
        return 20 <= x <= 24

    poles, why = _plan(lua, start, goal, blocked=blocked)
    assert why is None
    assert all(not blocked(x, y) for x, y in poles)
    assert all(y == 0.5 for _, y in poles)
    assert max(_spans(start, poles)) <= 7.5
    assert len(poles) <= 10


def test_a_lake_wider_than_the_reach_needs_the_walking_path_as_guide():
    lua, _ = _lua()
    start, goal = (0.5, 0.5), (60.5, 0.5)

    def lake(x, y):
        return 15 <= x <= 45 and -20 <= y <= 20

    poles, why = _plan(lua, start, goal, blocked=lake)
    assert poles is None
    assert "No placeable tile for a pole" in why
    guide = [(10.5, 0.5), (10.5, 25.5), (50.5, 25.5), (50.5, 0.5)]
    poles, why = _plan(lua, start, goal, blocked=lake, guide=guide)
    assert why is None, why
    assert all(not lake(x, y) for x, y in poles)
    assert max(_spans(start, poles)) <= 7.5
    assert poles[-1] == goal


def test_big_poles_span_30_tiles_on_corner_positions():
    lua, _ = _lua()
    start, goal = (0, 0), (300, 0)
    poles, why = _plan(lua, start, goal, reach=30, offset=0, start_reach=30)
    assert why is None
    assert all(float(x).is_integer() and float(y).is_integer() for x, y in poles)
    assert len(poles) <= 11
    assert max(_spans(start, poles)) <= 30


def test_ending_at_a_pole_places_nothing_beside_it():
    lua, _ = _lua()
    start, goal = (0.5, 0.5), (30.5, 0.5)
    poles, why = _plan(lua, start, goal, goal_reach=7.5)
    assert why is None
    assert goal not in poles
    assert math.dist(poles[-1], goal) <= 7.5
    assert len(poles) == 4  # 7.5, 14.5, 21.5, 28.5
    assert max(_spans(start, poles + [goal])) <= 7.5


def test_a_source_that_is_not_a_pole_gets_the_first_pole_on_it():
    lua, _ = _lua()
    start, goal = (0.5, 0.5), (20.5, 0.5)
    poles, why = _plan(lua, start, goal, start_reach=None)
    assert why is None
    assert poles[0] == start
    assert len(poles) == 4


def test_real_call_needs_every_pole_in_the_inventory_and_puts_the_character_back():
    """storage.actions.connect_entities: per-item check before anything is built."""
    lua, state = _lua(
        poles=[("small-electric-pole", 0.5, 0.5)], items={"small-electric-pole": 3}
    )
    action = lua.eval("storage.actions.connect_entities")
    with pytest.raises(lupa.LuaError) as err:
        action(1, 0.5, 0.5, 50.5, 0.5, -1, "small-electric-pole", False, 3)
    assert "small-electric-pole: required 7, in inventory 3" in str(err.value)
    assert len(state.built) == 0, "nothing built"
    pos = lua.eval("storage.agent_characters[1].position")
    assert (pos.x, pos.y) == (0, 0)


def test_dry_run_and_real_call_place_the_same_poles():
    lua, state = _lua(
        poles=[("small-electric-pole", 0.5, 0.5)], items={"small-electric-pole": 20}
    )
    action = lua.eval("storage.actions.connect_entities")
    dry = action(1, 0.5, 0.5, 50.5, 0.5, -1, "small-electric-pole", True, 20)
    planned = [(dry.planned[i].x, dry.planned[i].y) for i in range(1, len(dry.planned) + 1)]
    real = action(1, 0.5, 0.5, 50.5, 0.5, -1, "small-electric-pole", False, 20)
    built = [(state.built[i].position.x, state.built[i].position.y) for i in range(1, len(state.built) + 1)]
    assert planned == built
    assert real.number_of_entities == len(built) == 7
    assert state.inv["small-electric-pole"] == 13
    assert lua.eval("storage.elapsed_ticks") == 0, "no walking-time counter: the client walks"


def test_wire_reach_falls_back_to_the_game_values():
    lua, _ = _lua()
    reach = lua.eval("storage.utils.pole_wire_reach")
    assert reach("small-electric-pole") == 7.5
    assert reach("medium-electric-pole") == 9
    assert reach("big-electric-pole") == 30
    assert reach("substation") == 18
    offset = lua.eval("storage.utils.pole_grid_offset")
    assert offset("small-electric-pole") == 0.5
    assert offset("big-electric-pole") == 0
