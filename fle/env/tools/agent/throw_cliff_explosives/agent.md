# throw_cliff_explosives

## Overview

The `throw_cliff_explosives` tool throws one cliff-explosives (`Prototype.CliffExplosives`) at a position, as a player throws the capsule. Every cliff within the explosion radius (1.5 tiles) of the position is destroyed, and the ground under it can then be built on.

## Function Signature

```python
def throw_cliff_explosives(position: Position) -> List[Position]
```

### Parameters

- `position`: the position to throw at

### Returns

- The positions of the cliffs that were destroyed (an empty list if none was in the radius)

## Usage Example

```python
move_to(Position(x=-240, y=-281))
destroyed = throw_cliff_explosives(Position(x=-246, y=-281.5))
print(f"Destroyed {len(destroyed)} cliffs: {destroyed}")
```

## Key Behaviors

- The position must be within the throw range (10 tiles) of your character
- One cliff-explosives is used per throw, even if no cliff is in the radius
- Cliffs near the ones destroyed may change shape, as in the game

## Error Handling

The tool raises an error, and uses no item, if:
- there is no cliff-explosives in your inventory
- the position is out of throw range
