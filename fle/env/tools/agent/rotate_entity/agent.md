# rotate_entity

The `rotate_entity` tool allows you to change the orientation of placed entities in Factorio. Different entities have different rotation behaviors and requirements.

## Basic Usage

```python
rotate_entity(entity: Entity, direction: Direction = Direction.UP) -> Entity
```

Returns the rotated Entity object.

### Parameters

- `entity`: Entity to rotate
- `direction`: Target direction (UP/DOWN/LEFT/RIGHT)

### Examples

```python
# Rotating inserters - Inserter rotation affects pickup/drop positions
# Important: By default inserters take from entities they are placed next to
# Always rotate the inserters the other way if they need to take items from an entity
inserter = place_entity(Prototype.BurnerInserter, position=pos, direction = Direction.UP)
print(f"Original inserter: pickup={inserter.pickup_position}, drop={inserter.drop_position}")
inserter = rotate_entity(inserter, Direction.DOWN)
print(f"Rotated inserter: pickup={inserter.pickup_position}, drop={inserter.drop_position}")
```

## Entity-Specific Behaviors

### 1. Assembling Machines, Oil Refineries and Chemical Plants

Rotating keeps the recipe, items and fluids. In Factorio 2.0:
- Chemical plants and oil refineries can be rotated with or without a recipe
- Assembling machines 2 and 3 can only be rotated while their recipe uses a fluid (their fluid connections are off otherwise)
- Assembling machine 1 has no fluid connections and always faces north

```python
assembler = place_entity(Prototype.AssemblingMachine2, position=pos)
assembler = set_entity_recipe(assembler, Prototype.IronGearWheel)

# Raises: the recipe uses no fluid, so the machine keeps facing north
try:
    assembler = rotate_entity(assembler, Direction.RIGHT)
except Exception as e:
    print(e)

# A recipe with a fluid ingredient turns the fluid connections on
assembler = set_entity_recipe(assembler, RecipeName.FillWaterBarrel)
assembler = rotate_entity(assembler, Direction.RIGHT)
```
