"""The observation's Machine Status section: counts per machine and recipe with
the game's reasons (no server)."""

from fle.env.entities import (
    AssemblingMachine,
    Dimensions,
    EntityStatus,
    Furnace,
    Position,
    Recipe,
    TileDimensions,
)
from fle.env.gym_env import observation_formatter as of
from fle.env.gym_env.observation_formatter import TreeObservationFormatter as T

MISSING = "missing iron-plate (0 of 1 per craft)"


def _machine(recipe="iron-gear-wheel", status=EntityStatus.WORKING, detail=None, x=0):
    return AssemblingMachine(
        name="assembling-machine-1",
        type="assembling-machine",
        position=Position(x=1.5 + 3 * x, y=1.5),
        energy=0,
        dimensions=Dimensions(width=3, height=3),
        tile_dimensions=TileDimensions(tile_width=3, tile_height=3),
        health=100,
        recipe=Recipe(name=recipe) if recipe else None,
        status=status,
        status_detail=detail,
    ).__dict__


def test_counts_per_recipe_with_reasons():
    entities = [
        _machine(x=0),
        _machine(x=1),
        _machine(status=EntityStatus.ITEM_INGREDIENT_SHORTAGE, detail=MISSING, x=2),
        _machine(recipe=None, status=EntityStatus.NO_RECIPE, detail="no recipe set"),
    ]
    text = T.format_machine_status(entities)
    assert text.splitlines() == [
        "### Machine Status",
        "- assembling-machine-1 [iron-gear-wheel]: 3 (2 working, 1 " + MISSING + ")",
        "- assembling-machine-1 [no recipe]: 1 (1 no recipe set)",
    ]


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
    assert "- stone-furnace: 1 (1 no ingredients)" in T.format_machine_status([furnace])


def test_no_machines_no_section():
    assert T.format_machine_status([]) == ""
    assert (
        T.format_machine_status([{"name": "wooden-chest", "type": "container"}]) == ""
    )


def test_lines_and_states_are_capped():
    many_recipes = [
        _machine(recipe=f"recipe-{i:02d}") for i in range(of.MACHINE_LINES_SHOWN + 3)
    ]
    lines = T.format_machine_status(many_recipes).splitlines()
    assert len(lines) == 1 + of.MACHINE_LINES_SHOWN + 1
    assert lines[-1] == "- (3 more)"

    states = [
        _machine(
            status=EntityStatus.NO_POWER, detail=f"no power (electric network {i})"
        )
        for i in range(of.MACHINE_STATES_SHOWN + 2)
    ] + [_machine()]
    line = T.format_machine_status(states).splitlines()[1]
    assert line.startswith("- assembling-machine-1 [iron-gear-wheel]: 7 (1 working, ")
    assert line.endswith(", (3 more))")
    assert line.count("no power") == of.MACHINE_STATES_SHOWN - 1


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
