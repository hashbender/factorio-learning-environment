"""Belt groups in the observation: per-lane contents, capped lists (no server)."""

from fle.env.entities import (
    BeltGroup,
    Dimensions,
    Direction,
    Inventory,
    Position,
    TileDimensions,
    TransportBelt,
)
from fle.env.gym_env.observation_formatter import TreeObservationFormatter as T
from fle.env.tools.agent.connect_entities.groupable_entities import _construct_group


def _belt(x, left=None, right=None, warnings=None, terminus=False, source=False):
    return TransportBelt(
        name="transport-belt",
        position=Position(x=x, y=3.5),
        direction=Direction.EAST,
        input_position=Position(x=x - 1, y=3.5),
        output_position=Position(x=x + 1, y=3.5),
        energy=0,
        dimensions=Dimensions(width=1, height=1),
        tile_dimensions=TileDimensions(tile_width=1, tile_height=1),
        health=150,
        inventory={
            "left": Inventory(**(left or {})),
            "right": Inventory(**(right or {})),
        },
        warnings=warnings or [],
        is_terminus=terminus,
        is_source=source,
    )


def _group(belts):
    return BeltGroup(
        id=1,
        belts=belts,
        inputs=[b for b in belts if b.is_source],
        outputs=[b for b in belts if b.is_terminus],
        position=belts[0].position,
    )


def test_lanes_are_reported_separately():
    belts = [
        _belt(0.5, left={"iron-ore": 3}, source=True),
        _belt(1.5, right={"coal": 2}),
        _belt(2.5, terminus=True),
    ]
    text = T.format_entities([_group(belts).__dict__])
    assert "lanes=L[iron-ore:3] R[coal:2]" in text
    assert "holding=2 belts: (0.5, 3.5) L[iron-ore:3]; (1.5, 3.5) R[coal:2]" in text
    assert "belts=transport-belt:3" in text
    assert "inputs=[(0.5, 3.5)]" in text and "outputs=[(2.5, 3.5)]" in text


def test_holding_list_is_capped_with_more_marker():
    belts = [_belt(i + 0.5, left={"iron-plate": 1}) for i in range(20)]
    text = T.format_entities([_group(belts).__dict__])
    assert "holding=20 belts:" in text
    assert f"({20 - T.BELT_CONTENTS_CAP} more)" in text
    # a 20-belt group must not list every belt
    assert text.count("L[iron-plate:1]") == T.BELT_CONTENTS_CAP


def test_belt_list_does_not_collapse_to_first_position():
    belts = [_belt(i + 0.5) for i in range(4)]
    text = T.format_entities([_group(belts).__dict__])
    # Before: "belts=(0.5, 3.5)" (a list of belts read as one Position)
    assert "belts=(0.5, 3.5)" not in text
    assert "belts=transport-belt:4" in text


def test_single_position_still_cleaned():
    assert T.format_value("position", "Position(x=1.5, y=-2.0)") == "(1.5, -2.0)"


def test_group_full_output_only_when_an_end_is_full():
    mid_full = [
        _belt(0.5, left={"coal": 1}, source=True),
        _belt(
            1.5, left={"coal": 8}, right={"coal": 8}, warnings=["Belt output is full"]
        ),
        _belt(2.5, left={"coal": 1}, terminus=True),
    ]
    g = _construct_group(0, mid_full, None, mid_full[0].position)
    assert g.status.name != "FULL_OUTPUT"
    end_full = mid_full[:2] + [
        _belt(2.5, left={"coal": 8}, warnings=["Belt output is full"], terminus=True)
    ]
    g = _construct_group(0, end_full, None, end_full[0].position)
    assert g.status.name == "FULL_OUTPUT"


def test_belt_group_repr_has_lane_totals():
    belts = [_belt(0.5, left={"iron-ore": 2}), _belt(1.5, right={"coal": 1})]
    r = repr(_group(belts))
    assert "left_lane={'iron-ore': 2}" in r and "right_lane={'coal': 1}" in r
