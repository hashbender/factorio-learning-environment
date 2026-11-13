"""The observation's Machine Status section: counts per machine and recipe with
the game's reasons, and the position of every machine that is not working
(no server)."""

from fle.env.entities import (
    AssemblingMachine,
    Dimensions,
    EntityStatus,
    Furnace,
    Inserter,
    Position,
    Recipe,
    TileDimensions,
)
from fle.env.gym_env import observation_formatter as of
from fle.env.gym_env.observation_formatter import TreeObservationFormatter as T

MISSING = "missing iron-plate (0 of 1 per craft)"


def _machine(
    recipe="iron-gear-wheel", status=EntityStatus.WORKING, detail=None, x=0, y=0
):
    return AssemblingMachine(
        name="assembling-machine-1",
        type="assembling-machine",
        position=Position(x=1.5 + 3 * x, y=1.5 + 3 * y),
        energy=0,
        dimensions=Dimensions(width=3, height=3),
        tile_dimensions=TileDimensions(tile_width=3, tile_height=3),
        health=100,
        recipe=Recipe(name=recipe) if recipe else None,
        status=status,
        status_detail=detail,
    ).__dict__


def _inserter(status=EntityStatus.WORKING, detail=None, x=0, name="inserter"):
    return Inserter(
        name=name,
        type="inserter",
        position=Position(x=0.5 + x, y=4.5),
        energy=0,
        dimensions=Dimensions(width=1, height=1),
        tile_dimensions=TileDimensions(tile_width=1, tile_height=1),
        health=100,
        status=status,
        status_detail=detail,
        pickup_position=Position(x=0.5 + x, y=3.5),
        drop_position=Position(x=0.5 + x, y=5.5),
    ).__dict__


def test_counts_per_recipe_with_reasons_and_positions():
    entities = [
        _machine(x=0),
        _machine(x=1),
        _machine(status=EntityStatus.ITEM_INGREDIENT_SHORTAGE, detail=MISSING, x=2),
        _machine(recipe=None, status=EntityStatus.NO_RECIPE, detail="no recipe set"),
    ]
    text = T.format_machine_status(entities)
    assert text.splitlines() == [
        "### Machine Status",
        "- assembling-machine-1 [iron-gear-wheel]: 3 (2 working, 1 "
        + MISSING
        + " at (7.5, 1.5))",
        "- assembling-machine-1 [no recipe]: 1 (1 no recipe set at (1.5, 1.5))",
    ]


def test_machines_with_the_same_reason_share_one_position_list():
    entities = [
        _machine(status=EntityStatus.ITEM_INGREDIENT_SHORTAGE, detail=MISSING, y=i)
        for i in range(3)
    ] + [_machine(x=1)]
    assert T.format_machine_status(entities).splitlines()[1] == (
        "- assembling-machine-1 [iron-gear-wheel]: 4 (1 working, 3 "
        + MISSING
        + " at (1.5, 1.5..7.5 by 3))"
    )


def test_working_machines_are_counts_without_positions():
    lines = T.format_machine_status([_machine(x=0), _machine(x=1)]).splitlines()
    assert lines == [
        "### Machine Status",
        "- assembling-machine-1 [iron-gear-wheel]: 2 (2 working)",
    ]


def test_inserters_are_listed_with_their_reason():
    wait = "waiting for items from iron-chest at (1.5, 3.5)"
    entities = [
        _inserter(x=0),
        _inserter(status=EntityStatus.WAITING_FOR_SOURCE_ITEMS, detail=wait, x=1),
        _inserter(status=EntityStatus.NO_POWER, x=2, name="fast-inserter"),
    ]
    assert T.format_machine_status(entities).splitlines() == [
        "### Machine Status",
        "- fast-inserter: 1 (1 no power at (2.5, 4.5))",
        # r22: the group key drops the target's position (lines group by kind of wait)
        "- inserter: 2 (1 working, 1 waiting for items from iron-chest at (1.5, 4.5))",
    ]


def test_machine_without_a_position_is_still_counted():
    machine = _machine(status=EntityStatus.NO_POWER)
    machine["position"] = None
    assert T.format_machine_status([machine]).splitlines()[1] == (
        "- assembling-machine-1 [iron-gear-wheel]: 1 "
        "(1 no power at (1 without a position))"
    )


def test_status_without_detail_uses_the_status_name():
    furnace = Furnace(
        name="stone-furnace",
        type="furnace",
        position=Position(x=0, y=0),
        energy=0,
        dimensions=Dimensions(width=2, height=2),
        tile_dimensions=TileDimensions(tile_width=2, tile_height=2),
        health=100,
        status=EntityStatus.NO_INGREDIENTS,
    ).__dict__
    assert "- stone-furnace: 1 (1 no ingredients at (0, 0))" in T.format_machine_status(
        [furnace]
    )


def test_no_machines_no_section():
    assert T.format_machine_status([]) == ""
    assert (
        T.format_machine_status([{"name": "wooden-chest", "type": "container"}]) == ""
    )


def test_only_all_working_lines_are_capped():
    many_recipes = [
        _machine(recipe=f"recipe-{i:02d}") for i in range(of.MACHINE_LINES_SHOWN + 3)
    ]
    lines = T.format_machine_status(many_recipes).splitlines()
    assert len(lines) == 1 + of.MACHINE_LINES_SHOWN + 1
    assert lines[-1] == "- (3 more, all working)"

    # lines with a machine that is not working are all listed
    stalled = [
        _machine(
            recipe=f"recipe-{i:02d}",
            status=EntityStatus.ITEM_INGREDIENT_SHORTAGE,
            detail=MISSING,
            x=i,
        )
        for i in range(of.MACHINE_LINES_SHOWN + 3)
    ]
    lines = T.format_machine_status(many_recipes + stalled).splitlines()
    assert len(lines) == 1 + of.MACHINE_LINES_SHOWN + 3
    for i in range(of.MACHINE_LINES_SHOWN + 3):
        assert f"1 {MISSING} at ({1.5 + 3 * i:g}, 1.5)" in lines[1 + i]


def test_every_state_that_is_not_working_is_listed():
    states = [
        _machine(
            status=EntityStatus.NO_POWER,
            detail=f"no power (electric network {i})",
            x=i,
        )
        for i in range(9)
    ] + [_machine(x=9)]
    line = T.format_machine_status(states).splitlines()[1]
    assert line.startswith("- assembling-machine-1 [iron-gear-wheel]: 10 (1 working, ")
    assert "more" not in line
    for i in range(9):
        assert f"1 no power (electric network {i}) at ({1.5 + 3 * i:g}, 1.5)" in line


def test_section_size_is_capped_with_whole_lines_and_a_count():
    def stalled(recipes, per_recipe=4):
        return [
            _machine(
                recipe=f"recipe-{r:03d}",
                status=EntityStatus.ITEM_INGREDIENT_SHORTAGE,
                detail=f"missing item-{r}-{i} (0 of 1 per craft)",
                x=i,
                y=r,
            )
            for r in range(recipes)
            for i in range(per_recipe)
        ]

    small = T.format_machine_status(stalled(5))
    assert len(small) < of.MACHINE_SECTION_CHARS and "not listed" not in small

    entities = stalled(60) + [_machine(recipe="recipe-059", x=9)]
    text = T.format_machine_status(entities)
    assert len(text) <= of.MACHINE_SECTION_CHARS
    lines = text.splitlines()
    uncapped_lines = {
        T.format_machine_status(
            [e for e in entities if e["recipe"].name == f"recipe-{r:03d}"]
        ).splitlines()[1]
        for r in range(60)
    }
    shown = lines[1:-1]
    assert shown and all(line in uncapped_lines for line in shown)  # whole lines
    left_out = 60 - len(shown)
    assert left_out > 0
    assert lines[-1] == (
        f"- ({4 * left_out} more non-working machines and "
        "1 more working machines not listed)"
    )
    only_stalled = T.format_machine_status(stalled(60)).splitlines()
    assert only_stalled[-1] == (
        f"- ({4 * (60 - len(only_stalled[1:-1]))} more non-working machines not listed)"
    )


def test_section_follows_the_entities():
    from fle.env.gym_env.observation import Observation

    obs = Observation.from_dict(
        {
            "entities": [
                _machine(status=EntityStatus.ITEM_INGREDIENT_SHORTAGE, detail=MISSING)
            ]
        }
    )
    raw = T().format(obs).raw_str
    assert raw.index("### Entities") < raw.index("### Machine Status")
    off = T(include_machine_status=False).format(obs).raw_str
    assert "### Machine Status" not in off
