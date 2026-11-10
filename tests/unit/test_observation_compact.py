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


# --- complete listing: belts, notes, never dropping types ---------------------

from fle.env.entities import BeltGroup, TransportBelt  # noqa: E402
from fle.env.gym_env.entity_compact import _points, compact_section  # noqa: E402


def _belt(x, y, direction=Direction.EAST, left=None):
    return TransportBelt(
        name="transport-belt",
        position=Position(x=x, y=y),
        direction=direction,
        input_position=Position(x=x - 1, y=y),
        output_position=Position(x=x + 1, y=y),
        inventory={"left": Inventory(**(left or {})), "right": Inventory()},
        **_dims(1),
    )


def _belt_factory(groups=12, length=40):
    out = []
    for g in range(groups):
        y = 0.5 + 4 * g
        belts = [
            _belt(x + 0.5, y, left={"iron-plate": 1 + (x + g) % 4})
            for x in range(length)
        ]
        out.append(
            BeltGroup(
                id=g,
                belts=belts,
                inputs=[belts[0]],
                outputs=[belts[-1]],
                position=belts[0].position,
            ).__dict__
        )
    return out


def test_within_lists_every_belt_when_it_fits():
    ents = _belt_factory(groups=1, length=10)
    text = T.format_entities_within(ents, 100_000)
    assert "more)" not in text
    assert "holding=10 belts:" in text
    assert text.count("L[iron-plate:") == 10 + 1  # every belt, plus the lane total
    assert f"belt_positions={Direction.EAST.name} (0.5..9.5 by 1, 0.5)" in text


def test_belt_factory_fits_and_says_what_was_summarized():
    ents = _belt_factory() + _factory(2, 6)
    budget = 3000
    text = T.format_entities_within(ents, budget)
    assert len(text) <= budget, len(text)
    counts = dict(re.findall(r"^- ([\w-]+): (\d+)$", text, re.M))
    assert counts == {
        "belt-group": "12",
        "inserter": "12",
        "stone-furnace": "12",
        "assembling-machine-1": "10",
    }
    assert "Summarized to fit 3000 chars: " in text
    assert "belt-group x12 (" in text
    assert "more)" not in text and "omitted" not in text


def test_types_are_never_cut():
    groups = {f"type-{i:02d}": [{"position": f"({i}.5, 0.5)"}] for i in range(40)}
    text = compact_section(groups, 200)
    for i in range(40):
        assert f"type-{i:02d}: 1" in text
    assert "counts only" in text


def test_reduction_is_uniform_across_types():
    # a big and a small type: the small one is summarised no further than the big one
    ents = _belt_factory(groups=12) + _factory(1, 3)
    text = T.format_entities_within(ents, 2500)
    assert "belt-group x12 (" in text
    big = re.search(r"belt-group x12 \(([^)]*)\)", text).group(1)
    small = re.search(r"stone-furnace x3 \(([^)]*)\)", text)
    if small and "count, status and area only" in small.group(1):
        assert "count, status and area only" in big


def test_points_expand_runs():
    pts = _points("EAST (0.5..2.5 by 1, 3.5) (9.5, 1..3 by 2) +(1, 2)")
    assert sorted(pts) == [(0.5, 3.5), (1.5, 3.5), (2.5, 3.5), (9.5, 1.0), (9.5, 3.0)]
