"""TransportBelt.inventory always has both lanes (r17; the validator is in fle/env/belt_lanes.py). No server."""

import pytest

from fle.env.entities import (
    Dimensions,
    Direction,
    Inventory,
    Position,
    TileDimensions,
    TransportBelt,
    UndergroundBelt,
)


def _belt(cls=TransportBelt, **extra):
    kw = dict(
        name="transport-belt",
        position=Position(x=0.5, y=0.5),
        direction=Direction.EAST,
        input_position=Position(x=-0.5, y=0.5),
        output_position=Position(x=1.5, y=0.5),
        energy=0,
        dimensions=Dimensions(width=1, height=1),
        tile_dimensions=TileDimensions(tile_width=1, tile_height=1),
        health=150,
    )
    kw.update(extra)
    return cls(**kw)


@pytest.mark.parametrize(
    "inventory",
    [{"left": {"iron-plate": 4}}, {"right": {"coal": 1}}, {}, [], None, {"left": {}, "right": {}}],
)
def test_both_lanes_present(inventory):
    b = _belt(inventory=inventory)
    assert set(b.inventory) == {"left", "right"}


def test_loaded_lane_kept_empty_lane_added():
    b = _belt(inventory={"left": {"iron-plate": 4}})
    assert dict(Inventory.model_validate(b.inventory["left"]).items()) == {"iron-plate": 4}
    assert len(dict(Inventory.model_validate(b.inventory["right"]).items())) == 0
    assert b.inventory["right"].get("iron-plate", 0) == 0


def test_underground_belt_inherits():
    u = _belt(UndergroundBelt, name="underground-belt", is_input=True, inventory={"right": {"coal": 2}})
    assert set(u.inventory) == {"left", "right"}


def test_validator_not_in_the_types_block():
    """The agents' types block (CodeAnalyzer over entities.py) shows no validator line for it."""
    from pathlib import Path

    from fle.env.utils.controller_loader.code_analyzer import CodeAnalyzer

    text = CodeAnalyzer.parse_file_for_structure(
        str(Path(__file__).resolve().parents[2] / "fle/env/entities.py")
    )
    assert "both_lanes" not in text
