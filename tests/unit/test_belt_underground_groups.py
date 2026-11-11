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
    assert ug.id == 3189 and ug.connected_to == 3190
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
