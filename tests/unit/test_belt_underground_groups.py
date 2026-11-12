"""Underground belt pairs in get_entities belt grouping (no server).

Regression: a basic underground pair 5 tiles apart (the game's max for
underground-belt) was not linked by the walker (hard-coded range 4), so its two
ends landed in different belt groups and consolidate_underground_belts raised
KeyError on the partner id, which failed every observation for the world.
"""

from fle.env.entities import (
    BeltGroup,
    Dimensions,
    Direction,
    Inventory,
    Position,
    TileDimensions,
    TransportBelt,
    UndergroundBelt,
)
from fle.env.game_types import Prototype
from fle.env.tools.agent.connect_entities.groupable_entities import (
    agglomerate_groupable_entities,
    consolidate_underground_belts,
)

Y = 28.5
COMMON = dict(
    direction=Direction.EAST,
    energy=0,
    dimensions=Dimensions(width=1, height=1),
    tile_dimensions=TileDimensions(tile_width=1, tile_height=1),
    health=150,
    inventory={"left": Inventory(), "right": Inventory()},
)


def _belt(x, uid):
    return TransportBelt(
        name="transport-belt",
        id=uid,
        position=Position(x=x, y=Y),
        input_position=Position(x=x - 1, y=Y),
        output_position=Position(x=x + 1, y=Y),
        prototype=Prototype.TransportBelt,
        **COMMON,
    )


def _ug(x, uid, is_input, partner, name="underground-belt", proto=None):
    return UndergroundBelt(
        name=name,
        id=uid,
        position=Position(x=x, y=Y),
        input_position=Position(x=x - 1, y=Y),
        output_position=Position(x=x + 1, y=Y),
        is_input=is_input,
        connected_to=partner,
        prototype=proto or Prototype.UndergroundBelt,
        **COMMON,
    )


def _line(gap, name="underground-belt", proto=None):
    """belt -> entrance ... (gap tiles) ... exit -> belt, ids as in the live world."""
    a, b = 9.5, 9.5 + gap
    return [
        _belt(a - 1, 3001),
        _ug(a, 3189, True, 3190, name, proto),
        _ug(b, 3190, False, 3189, name, proto),
        _belt(b + 1, 3002),
    ]


def _belt_groups(groups):
    return [g for g in groups if isinstance(g, BeltGroup)]


def _undergrounds(group):
    return [b for b in group.belts if isinstance(b, UndergroundBelt)]


def test_pair_at_max_distance_is_one_group_and_consolidated():
    groups = _belt_groups(agglomerate_groupable_entities(_line(5)))
    assert len(groups) == 1
    (ug,) = _undergrounds(groups[0])
    assert ug.id == 3189 and ug.is_input
    assert ug.connected_to is None  # the exit is not listed on its own
    assert ug.position == Position(x=9.5, y=Y)
    assert ug.output_position == Position(x=14.5, y=Y)
    assert len(groups[0].belts) == 3  # belt, consolidated underground, belt


def test_short_pair_still_consolidated():
    groups = _belt_groups(agglomerate_groupable_entities(_line(3)))
    assert len(groups) == 1 and len(_undergrounds(groups[0])) == 1


def test_fast_underground_pair_at_seven_tiles():
    belts = _line(7, "fast-underground-belt", Prototype.FastUndergroundBelt)
    groups = _belt_groups(agglomerate_groupable_entities(belts))
    assert len(groups) == 1 and len(_undergrounds(groups[0])) == 1


def test_partner_outside_group_does_not_raise():
    # Exit whose entrance is not in this group (e.g. outside the query radius).
    exit_only = _ug(14.5, 3190, False, 3189)
    group = BeltGroup(id=0, belts=[exit_only], inputs=[], outputs=[], position=exit_only.position)
    (out,) = consolidate_underground_belts([group])
    assert out.belts == [exit_only]
    assert out.belts[0].connected_to == 3189


def test_lone_end_without_partner_in_set_is_kept():
    belts = [_belt(8.5, 3001), _ug(9.5, 3189, True, 9999)]
    groups = _belt_groups(agglomerate_groupable_entities(belts))
    ugs = [u for g in groups for u in _undergrounds(g)]
    assert [u.id for u in ugs] == [3189]


def _ids(group):
    return {b.id for b in group.belts}


def test_consolidated_pair_points_at_no_removed_id():
    """connected_to used to name the exit, which the merge had removed from the group."""
    groups = _belt_groups(agglomerate_groupable_entities(_line(4)))
    for g in groups:
        for b in g.belts:
            if isinstance(b, UndergroundBelt) and b.connected_to is not None:
                assert b.connected_to in _ids(g)


def test_exit_listed_first_still_merges_from_the_entrance():
    """Pairing took the first end in the list as the entrance; with the exit first the
    merged entity was reversed (position = exit, output_position = entrance)."""
    belt_in, entrance, exit_, belt_out = _line(4)
    group = BeltGroup(
        id=0,
        belts=[belt_in, exit_, entrance, belt_out],
        inputs=[],
        outputs=[],
        position=entrance.position,
    )
    (out,) = consolidate_underground_belts([group])
    (ug,) = _undergrounds(out)
    assert ug.id == 3189 and ug.is_input
    assert ug.position == Position(x=9.5, y=Y)
    assert ug.output_position == Position(x=13.5, y=Y)
    assert ug.input_position == Position(x=8.5, y=Y)
    assert ug.connected_to is None
    assert len(out.belts) == 3
