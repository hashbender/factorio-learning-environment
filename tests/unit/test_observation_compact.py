"""Compact entity section: bounded size, nothing silently dropped (no server)."""

import re

from fle.env.entities import (
    AssemblingMachine,
    Dimensions,
    Direction,
    EntityStatus,
    Furnace,
    Inserter,
    Inventory,
    Position,
    TileDimensions,
)
from fle.env.gym_env.entity_compact import positions_text
from fle.env.gym_env.observation_formatter import TreeObservationFormatter as T


def _dims(n):
    return dict(
        energy=0,
        dimensions=Dimensions(width=n - 0.6, height=n - 0.6),
        tile_dimensions=TileDimensions(tile_width=n, tile_height=n),
        health=150,
    )


def _factory(rows=6, per_row=12):
    out = []
    for r in range(rows):
        y = 10.5 + 6 * r
        for i in range(per_row):
            x = 0.5 + i
            out.append(
                Inserter(
                    name="inserter",
                    position=Position(x=x, y=y),
                    direction=Direction.UP,
                    pickup_position=Position(x=x, y=y + 1),
                    drop_position=Position(x=x, y=y - 1),
                    status=EntityStatus.WORKING if i % 5 else EntityStatus.NO_POWER,
                    **_dims(1),
                ).__dict__
            )
            out.append(
                Furnace(
                    name="stone-furnace",
                    position=Position(x=x * 2, y=y - 2),
                    fuel=Inventory(coal=(i * 7 + r) % 13 + 1),
                    furnace_source=Inventory(**{"iron-ore": i % 3}),
                    status=EntityStatus.WORKING,
                    **_dims(2),
                ).__dict__
            )
    for i in range(10):
        out.append(
            AssemblingMachine(
                name="assembling-machine-1",
                position=Position(x=40.5 + 3 * i, y=0.5),
                status=EntityStatus.WORKING,
                **_dims(3),
            ).__dict__
        )
    return out


def test_full_listing_kept_when_it_fits():
    ents = _factory(1, 3)
    full = T.format_entities(ents)
    assert T.format_entities_within(ents, len(full) + 10) == full


def test_compact_fits_budget_and_counts_every_entity():
    ents = _factory()
    full = T.format_entities(ents)
    for budget in (len(full) // 2, len(full) // 5, 2500, 900, 300):
        text = T.format_entities_within(ents, budget)
        assert len(text) <= budget, (budget, len(text))
        counts = dict(re.findall(r"- ([\w-]+): (\d+)\n", text + "\n"))
        if "counts only" not in text:
            assert counts == {
                "assembling-machine-1": "10",
                "inserter": "72",
                "stone-furnace": "72",
            }
        assert "omitted" not in text


def test_lossless_level_keeps_every_position_and_state():
    ents = _factory(2, 6)
    full = T.format_entities(ents)
    text = T.format_entities_compact(ents, len(full))
    assert "compact listing" in text
    # inserter geometry becomes relative and is shared by all of them
    assert "drop_position=+(0, -1)" in text and "pickup_position=+(0, 1)" in text
    # each furnace fuel value is still present (lossless level)
    assert "=varies" not in text
    for row in (10.5, 16.5):
        assert f"(0.5..5.5 by 1, {row:g})" in text or f"{row:g}" in text


def test_summaries_are_stated():
    ents = _factory()
    text = T.format_entities_compact(ents, 1500)
    assert len(text) <= 1500
    assert "=varies" in text or "not listed, to fit the size limit" in text


def test_positions_runs():
    pts = [(0.5 + i, 3.5) for i in range(5)] + [(9.5, 7.5)]
    assert positions_text(pts) == "(0.5..4.5 by 1, 3.5) (9.5, 7.5)"
