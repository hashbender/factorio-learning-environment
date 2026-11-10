# create_blueprint

## Overview

The `create_blueprint` tool saves entities you have built (your force's entities and ghosts) as a named blueprint, as the game's blueprint tool does: names, directions, recipes, modules and relative positions. Tiles are not included. Blueprints are kept with your world. Like the game's blueprint tool, it needs no research. `list_blueprints`, `get_blueprint` and `delete_blueprint` read and remove saved blueprints.

## Function Signature

```python
def create_blueprint(name: str, area: BoundingBox | tuple[Position, Position] = None, entities: list[Entity] = None) -> dict
def list_blueprints() -> list[dict]
def get_blueprint(name: str) -> dict
def delete_blueprint(name: str) -> bool
```

### Parameters

- `name`: 1 to 64 characters; an existing blueprint with the same name is replaced
- `area`: a `BoundingBox`, or a `(left_top, right_bottom)` pair of Positions; every entity of yours in it is included
- `entities`: entities (or entity groups) to include instead of an area

### Returns

- `create_blueprint`, `list_blueprints` (one per blueprint): `name`, `entity_count`, `entities` (count by name), `items` (items needed to build it), `width`, `height` (tiles)
- `get_blueprint`: the same, plus `entity_list`: `name`, `x`, `y` (relative to the blueprint's centre), `direction`, `recipe` for each entity

## Usage Example

```python
bp = create_blueprint("gears", area=(Position(x=10, y=10), Position(x=20, y=16)))
print(bp)
print(list_blueprints())
```

## Key Behaviors

- At most 20 blueprints, each of at most 500 entities
- Only your own entities are included (not trees, rocks, resources or characters)

## Error Handling

The tool raises an error if:
- the area has none of your entities, or a listed entity isn't one of yours
- the blueprint would have more than 500 entities, or 20 blueprints already exist under other names
- `get_blueprint` / `delete_blueprint`: no blueprint has that name
