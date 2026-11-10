# mark_for_deconstruction

## Overview

The `mark_for_deconstruction` tool marks entities for deconstruction, as the game's deconstruction planner does. Only construction robots remove marked entities, with the same needs as building ghosts (see `place_blueprint`): the research, a powered roboport with construction robots, the entity within a roboport's construction area. The robots take the entity's item and its contents to the network's storage chests. With an area, your entities, trees and rocks in it are marked. `cancel_deconstruction` removes the marks. `pickup_entity` still picks up marked entities by hand.

## Function Signature

```python
def mark_for_deconstruction(area: BoundingBox | tuple[Position, Position] = None, entities: list[Entity] = None) -> dict
def cancel_deconstruction(area: BoundingBox | tuple[Position, Position] = None, entities: list[Entity] = None) -> dict
```

### Returns

- `mark_for_deconstruction`: `marked`, `marked_by_name`, `already_marked`, `ghosts_removed` (ghosts are removed at once), `not_marked_count`, `not_marked` (up to 20: `name`, `x`, `y`, `reason`)
- `cancel_deconstruction`: `cancelled`, `cancelled_by_name`, `not_cancelled` (listed entities only: `name`, `x`, `y`, `reason`)

## Error Handling

The tool raises an error if neither an area nor entities are given.
