"""connect_entities with belts never changes belts that were already on the map,
unless allow_belt_changes=True is passed."""

import pytest

from fle.env.entities import Direction, Position
from fle.env.game_types import Prototype

BELTS = {Prototype.TransportBelt, Prototype.UndergroundBelt}


@pytest.fixture()
def game(instance):
    instance.initial_inventory = {
        **instance.initial_inventory,
        "transport-belt": 200,
        "underground-belt": 40,
        "burner-inserter": 5,
    }
    instance.reset()
    yield instance.namespace


def belt_states(game):
    """position -> (name, direction) for every belt on the map"""
    states = {}
    for group in game.get_entities(BELTS):
        for belt in getattr(group, "belts", [group]):
            states[(belt.position.x, belt.position.y)] = (belt.name, belt.direction)
    return states


def assert_kept(before, after):
    for pos, state in before.items():
        assert after.get(pos) == state, (
            f"existing belt at {pos} changed: {state} -> {after.get(pos)}"
        )


def line(game, start, end):
    return game.connect_entities(start, end, Prototype.TransportBelt)


def test_sideload_into_middle_keeps_line(game):
    """(a) a new line joins the side of an existing line"""
    main = line(game, Position(x=0, y=0), Position(x=10, y=0))
    before = belt_states(game)
    middle = main.belts[len(main.belts) // 2]
    merged = game.connect_entities(
        Position(x=5, y=6), middle.position, Prototype.TransportBelt
    )
    assert_kept(before, belt_states(game))
    assert len(merged.inputs) == 2 and len(merged.outputs) == 1


def test_extend_from_end_keeps_end_belt(game):
    """(b) a line continued from its end starts in front of the end belt"""
    main = line(game, Position(x=0, y=0), Position(x=5, y=0))
    before = belt_states(game)
    end = main.outputs[0]
    extended = game.connect_entities(main, Position(x=5, y=7), Prototype.TransportBelt)
    assert_kept(before, belt_states(game))
    positions = [b.position for b in extended.belts]
    assert any(p.is_close(end.output_position, 0.1) for p in positions)


def test_end_to_end_matching_direction(game):
    """(b) a new line runs into the start of an existing line"""
    line(game, Position(x=5, y=0), Position(x=10, y=0))
    before = belt_states(game)
    joined = game.connect_entities(
        Position(x=-2, y=0), Position(x=5, y=0), Prototype.TransportBelt
    )
    assert_kept(before, belt_states(game))
    assert len(joined.inputs) == 1 and len(joined.outputs) == 1


def test_cross_perpendicular_line_keeps_it(game):
    """(c) a route across an existing perpendicular line goes around it"""
    line(game, Position(x=6, y=-6), Position(x=6, y=6))
    before = belt_states(game)
    line(game, Position(x=0, y=0), Position(x=12, y=0))
    assert_kept(before, belt_states(game))


def test_route_next_to_parallel_line_keeps_it(game):
    """(c) a route that runs beside an existing line"""
    line(game, Position(x=0, y=1), Position(x=11, y=1))
    before = belt_states(game)
    line(game, Position(x=0, y=0), Position(x=11, y=0))
    assert_kept(before, belt_states(game))


def test_undergrounds_across_existing_line(game):
    """(d) undergrounds crossing an existing line"""
    line(game, Position(x=6, y=-6), Position(x=6, y=6))
    before = belt_states(game)
    game.connect_entities(Position(x=0, y=0), Position(x=12, y=0), BELTS)
    assert_kept(before, belt_states(game))


def test_branch_from_middle_fails_and_builds_nothing(game):
    """a line cannot start from a belt whose next tile is the same line"""
    main = line(game, Position(x=0, y=0), Position(x=10, y=0))
    before = belt_states(game)
    middle = main.belts[len(main.belts) // 2]
    with pytest.raises(Exception, match="already holds a transport-belt"):
        game.connect_entities(
            middle.position, Position(x=middle.position.x, y=7), Prototype.TransportBelt
        )
    assert belt_states(game) == before


def test_inserter_onto_wrong_way_belt_fails(game):
    """a route that would have to turn the belt under an inserter fails, naming it"""
    inserter = game.place_entity(
        Prototype.BurnerInserter, position=Position(x=0, y=-1), direction=Direction.DOWN
    )
    game.place_entity(
        Prototype.TransportBelt, position=inserter.drop_position, direction=Direction.UP
    )
    before = belt_states(game)
    with pytest.raises(Exception, match="existing transport-belt at .* facing UP"):
        game.connect_entities(
            inserter, Position(x=8, y=inserter.drop_position.y), Prototype.TransportBelt
        )
    assert belt_states(game) == before


def test_allow_belt_changes_turns_end_belt(game):
    """with allow_belt_changes=True the end belt may be turned to face the new belts"""
    main = line(game, Position(x=0, y=0), Position(x=5, y=0))
    end = main.outputs[0]
    game.connect_entities(
        main,
        Position(x=end.position.x, y=7),
        Prototype.TransportBelt,
        allow_belt_changes=True,
    )
    assert belt_states(game)[(end.position.x, end.position.y)][1] == Direction.DOWN
