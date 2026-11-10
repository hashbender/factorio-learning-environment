"""connect_entities(..., dry_run=True): the shape of the answer. Server-free."""

from fle.env.entities import ConnectDryRun, Direction, PlannedEntity, Position
from fle.env.tools.agent.connect_entities import dry_run as dr
from fle.env.tools.agent.connect_entities.client import ConnectEntities
from fle.env.tools.agent.connect_entities.path_result import PathResult
from fle.env.tools.agent.get_connection_amount.client import GetConnectionAmount
from fle.env.game_types import Prototype

import pytest

PLANNED = [
    {"name": "transport-belt", "x": 3.5, "y": 1.5, "direction": 8},
    {"name": "transport-belt", "x": 3.5, "y": 2.5, "direction": 8},
    {"name": "underground-belt", "x": 3.5, "y": 3.5, "direction": 8},
]


def _tool(legs, inventory=None):
    """A ConnectEntities whose legs answer from `legs` (a dict, an Exception or
    any other object standing for an existing group)."""
    tool = ConnectEntities.__new__(ConnectEntities)
    tool.player_index = 1
    tool._protected_belts = None
    answers = list(legs)
    seen = []

    def pair(source, target, connection_types=None, dry_run=False):
        assert dry_run is True
        seen.append((source, target))
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    tool._connect_pair_of_waypoints = pair
    tool.inspect_inventory = lambda: inventory or {}
    tool._snapshot_belts = lambda waypoints: None
    tool._get_connection_type = lambda prototype: None
    return tool, seen


def _leg(planned, available=4, would_turn=None):
    return {
        "number_of_entities_required": len(planned),
        "number_of_entities_available": available,
        "planned": planned,
        "would_turn": would_turn,
    }


def test_route_found_lists_what_would_be_placed():
    tool, _ = _tool([_leg(PLANNED)], {"transport-belt": 4})
    plan = tool.__call_impl__(
        Position(x=3.5, y=1.5), Position(x=3.5, y=3.5), Prototype.TransportBelt, dry_run=True
    )
    assert plan["route_found"] is True
    assert plan["required"] == {"transport-belt": 2, "underground-belt": 1}
    assert plan["in_inventory"] == {"transport-belt": 4, "underground-belt": 0}
    assert plan["missing"] == {"underground-belt": 1}
    assert plan["enough_in_inventory"] is False
    assert plan["number_of_entities_required"] == 3
    assert plan["number_of_entities_available"] == 4
    assert plan["error"] is None and plan["blocked_at"] is None
    assert isinstance(plan, ConnectDryRun) and plan.route_found is True
    first = plan.entities[0]
    assert isinstance(first, PlannedEntity)
    assert (first.name, first.position, first.direction) == (
        "transport-belt",
        Position(x=3.5, y=1.5),
        Direction.DOWN,
    )
    assert first["position"] == first.position  # dict-style reads work too
    assert "route_found" in plan.keys() and plan.get("error") is None
    assert repr(plan) == (
        "ConnectDryRun(route_found=True, required={'transport-belt': 2, 'underground-belt': 1}, "
        "in_inventory={'transport-belt': 4, 'underground-belt': 0}, missing={'underground-belt': 1}, "
        "entities=[transport-belt at (3.5, 1.5) DOWN, transport-belt at (3.5, 2.5) DOWN, "
        "underground-belt at (3.5, 3.5) DOWN])"
    )


def test_enough_in_inventory():
    tool, _ = _tool([_leg(PLANNED[:2])], {"transport-belt": 2})
    plan = tool.__call_impl__(
        Position(x=0, y=0), Position(x=1, y=1), Prototype.TransportBelt, dry_run=True
    )
    assert plan["missing"] == {} and plan["enough_in_inventory"] is True


def test_failed_route_does_not_raise_and_names_the_blocked_position():
    message = (
        "Failed to connect {'Pipe'} from x=3.5 y=1.5 to x=3.5 y=6.5. "
        "Cannot connect: cannot place pipe at (3.5, -4.5): blocked by stone-furnace"
    )
    tool, _ = _tool([Exception(message)])
    plan = tool.__call_impl__(
        Position(x=3.5, y=1.5), Position(x=3.5, y=6.5), Prototype.Pipe, dry_run=True
    )
    assert plan["route_found"] is False
    assert plan["error"] == message
    assert plan["blocked_at"] == Position(x=3.5, y=-4.5)
    assert plan["entities"] == [] and plan["required"] == {}
    assert plan["number_of_entities_required"] is None
    assert repr(plan) == f"ConnectDryRun(route_found=False, blocked_at=(3.5, -4.5), error={message!r})"


def test_failure_without_a_position():
    plan = dr.failure("Failed to connect {'Pipe'} from a to b. No path found")
    assert plan["blocked_at"] is None
    assert "blocked_at" not in repr(plan)


def test_each_leg_starts_at_its_own_waypoint():
    a, b, c = Position(x=0, y=0), Position(x=5, y=0), Position(x=5, y=5)
    tool, seen = _tool([_leg(PLANNED[:1]), _leg(PLANNED[1:])], {})
    plan = tool.__call_impl__(a, b, c, connection_type=Prototype.TransportBelt, dry_run=True)
    assert seen == [(a, b), (b, c)]
    assert plan["number_of_entities_required"] == 3


def test_a_leg_that_is_already_connected_places_nothing():
    tool, _ = _tool([object(), _leg(PLANNED[:1])], {})
    plan = tool.__call_impl__(
        Position(x=0, y=0),
        Position(x=5, y=0),
        Position(x=5, y=5),
        connection_type=Prototype.TransportBelt,
        dry_run=True,
    )
    assert plan["route_found"] is True and plan["number_of_entities_required"] == 1


TURN = {"name": "transport-belt", "x": 3.5, "y": 1.5, "from": 4, "to": 8}


def test_a_belt_that_would_be_turned_fails_the_dry_run_like_the_real_call():
    tool, _ = _tool([_leg(PLANNED, would_turn=TURN)], {})
    plan = tool.__call_impl__(
        Position(x=3.5, y=1.5), Position(x=3.5, y=3.5), Prototype.TransportBelt, dry_run=True
    )
    assert plan["route_found"] is False
    assert plan["error"] == (
        "This connection would change existing belts: transport-belt at (3.5, 1.5) facing RIGHT "
        "would be turned to face DOWN. Existing belts are only changed when "
        "allow_belt_changes=True is passed."
    )


def test_with_allow_belt_changes_the_turn_is_reported():
    tool, _ = _tool([_leg(PLANNED, would_turn=TURN)], {})
    plan = tool.__call_impl__(
        Position(x=3.5, y=1.5),
        Position(x=3.5, y=3.5),
        Prototype.TransportBelt,
        dry_run=True,
        allow_belt_changes=True,
    )
    assert plan["route_found"] is True
    assert plan["belt_changes"] == [
        "transport-belt at (3.5, 1.5) facing RIGHT would be turned to face DOWN"
    ]
    assert "belt_changes=" in repr(plan)


def test_long_routes_print_the_first_positions_only():
    planned = [{"name": "pipe", "x": i + 0.5, "y": 0.5, "direction": 0} for i in range(55)]
    plan = dr.success(dr.planned_entities(planned), {"pipe": 60}, 60)
    assert len(plan["entities"]) == 55
    assert plan["entities"][0].direction is None  # a pipe has no direction
    text = repr(plan)
    assert "pipe at (39.5, 0.5)" in text and "pipe at (40.5, 0.5)" not in text
    assert "... and 15 more in .entities" in text


def test_result_survives_being_rebuilt_field_by_field():
    """A process boundary that rebuilds FLE data models from their fields keeps the answer readable."""
    plan = dr.success(dr.planned_entities(PLANNED), {"transport-belt": 4}, 4)
    entities = [PlannedEntity.model_construct(**dict(e.__dict__)) for e in plan.entities]
    rebuilt = ConnectDryRun.model_construct(**{**dict(plan.__dict__), "entities": entities})
    assert repr(rebuilt) == repr(plan)
    assert rebuilt["required"] == {"transport-belt": 2, "underground-belt": 1}


def test_path_result_carries_the_plan():
    result = PathResult(
        {"number_of_entities": 2, "planned": {1: PLANNED[0], 2: PLANNED[1]}, "would_turn": {}}
    )
    assert result.planned == PLANNED[:2]
    assert result.would_turn is None
    assert PathResult("an error").planned == []
    assert PathResult({"number_of_entities": 0}).planned == []


def test_get_connection_amount_still_raises_without_a_route():
    tool = GetConnectionAmount.__new__(GetConnectionAmount)
    tool.connect_entities = lambda *a, **k: dr.failure("No path found")
    with pytest.raises(Exception) as e:
        tool(Position(x=0, y=0), Position(x=1, y=1), Prototype.Pipe)
    assert str(e.value) == "No path found"
    tool.connect_entities = lambda *a, **k: dr.success(
        dr.planned_entities(PLANNED), {}, 0
    )
    assert tool(Position(x=0, y=0), Position(x=1, y=1), Prototype.Pipe) == 3
