# place_entity

The `place_entity` tool allows you to place entities in the Factorio world while handling direction, positioning, and various entity-specific requirements. This guide explains how to use it effectively.

## Basic Usage

```python
place_entity(
    entity: Prototype,
    direction: Direction = Direction.UP,
    position: Position = Position(x=0, y=0),
    exact: bool = True,
    type: str = None
) -> Entity
```

Returns the placed Entity object.

### Parameters

- `entity`: Prototype of entity to place
- `direction`: Direction entity should face (default: UP)
- `position`: Where to place entity (default: 0,0)
- `exact`: Whether to require exact positioning (default: True)
- `type`: underground belts only: `"input"` or `"output"` end (default: chosen as described under Underground belts)

### Examples

```python
# first moveto target location
move_to(Position(x=0, y=0))
# Basic placement
chest = place_entity(Prototype.WoodenChest, position=Position(x=0, y=0))
# log your actions
print(f"Placed chest at {chest.position}")

# Directional placement
inserter = place_entity(
    Prototype.BurnerInserter,
    direction=Direction.RIGHT,
    position=Position(x=5, y=5)
)
# log your actions
print(f"Placed inserter at {inserter.position} to input into a chest")
move_to(water_pos)
# Flexible positioning
pump = place_entity(
    Prototype.OffshorePump,
    position=water_pos
)
# log your actions
print(f"Placed pump at {pump.position}to generate power")
```

### Mining Drills

```python
# Place on resource patch
ore_pos = nearest(Resource.IronOre)
move_to(ore_pos)
drill = place_entity(
    Prototype.BurnerMiningDrill,
    position=ore_pos,
    direction=Direction.DOWN
)
# log your actions
print(f"Placed drill at {drill.position} to mine iron ore")
```

### Pipe-to-ground

- For `Prototype.UndergroundPipe`, `direction` is the side its underground connection faces, towards the other end of its pair. Its above-ground connection is on the opposite side.
- Two pipe-to-ground on the same row or column whose underground sides face each other connect underground when they are at most 10 tiles apart (up to 9 tiles between them), e.g. `Direction.RIGHT` at (x, y) and `Direction.LEFT` at (x + 10, y).
- The returned entity, and `get_entities` / `get_entity`, report a pipe-to-ground's `direction` as the game stores it: the side of its above-ground connection, the opposite of the `direction` given to `place_entity`.

### Underground belts

- For `Prototype.UndergroundBelt`, `FastUndergroundBelt` and `ExpressUndergroundBelt`, `direction` is the belt's travel direction, for both ends.
- `type="input"` or `type="output"` builds that end. `type` on any other entity is an error.
- Without `type`, the new underground belt is an output end when the nearest underground belt of the same kind behind it (against its travel direction, at most 5 tiles back for `UndergroundBelt`, 7 for fast, 9 for express) travels the same way and is an input end with no partner yet; it then connects to that input. Otherwise it is an input end. So an entrance placed first and an exit placed after it, both with the same `direction`, connect.
- The returned `UndergroundBelt` has `is_input` (True for an input end) and `connected_to` (the id of the other end of its pair, if it has one).

### Building over an entity (fast replace)

- As in the game, an entity placed onto an entity of the same fast-replace group replaces it, e.g. a transport belt, underground belt or splitter onto any of these (a belt onto either tile of a splitter replaces the whole splitter), or a pipe onto a pipe-to-ground. The replaced entity's item goes back to your inventory (spilled at your feet if it does not fit), and the returned entity's `warnings` name what was replaced.

## Best Practices

- Use nearest buildable to ensure safe placement

## Common Patterns

1. **Mining Setup**
   You can put chests directly at the drop positions of drills to catch ore, thus creating automatic drilling lines

```python
def setup_mining(resource_pos: Position):
    move_to(resource_pos)
    # Place drill
    # put the drop position down
    drill = place_entity(
        Prototype.BurnerMiningDrill,
        position=resource_pos,
        direction=Direction.DOWN,
    )
    # log your actions
    print(f"Placed drill to mine iron ore at {drill.position}")
    # insert coal to drill
    drill = insert_item(Prototype.Coal, drill, quantity = 10)
    # Place output chest that catches ore
    chest = place_entity(
        Prototype.WoodenChest,
        position=drill.drop_position,
        direction=Direction.DOWN,
    )
    # log your actions
    print(f"Placed chest to catch iron ore at {chest.position}")
    # wait for 5 seconds and check if chest has the ore
    sleep(5)
    # update chest entity
    chest = get_entity(Prototype.WoodenChest, chest.position)
    assert inspect_inventory(entity=chest).get(Prototype.IronOre, 0) > 0, f"No iron ore found in chest at {chest.position}"
    return drill, chest
```
