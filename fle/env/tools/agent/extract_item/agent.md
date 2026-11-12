# extract_item

The extract tool allows you to remove items from entity inventories in the Factorio world. This tool is essential for moving items between entities and managing inventory contents.

## Basic Usage

```python
# Extract items using a position
extracted_count = extract_item(Prototype.IronPlate, position, quantity=5)

# Extract items using an entity directly
extracted_count = extract_item(Prototype.CopperCable, entity, quantity=3)
```

The function returns the number of items successfully extracted. The extracted items are automatically placed in the player's inventory.

## Parameters

- `entity`: The Prototype of the item to extract (required)
- `source`: Either a Position or Entity to extract from (required)
- `quantity`: Number of items to extract (default=5)

**Source Handling**

- Items come only from the entity that occupies the position (with an Entity: that entity, at its position), never from a neighbouring entity. A position on the edge shared by two entities belongs to the one to its right / below
- If no entity is at the position (or the Entity is gone), or that entity does not hold the item, the call raises an error that names up to 3 of the nearest entities within 10 tiles that hold the item
- If the entity at the position is a belt, items are taken off its lanes, as a player picks them up; the entity must be within reach

**Quantity Handling**

- If requested quantity exceeds available items, it extracts all available items
- Returns actual number of items extracted

## Examples

### Extracting from a Chest

```python
# Place a chest and insert items
chest = place_entity(Prototype.IronChest, position=Position(x=0, y=0))
insert_item(Prototype.IronPlate, chest, quantity=10)

# Extract using position
count = extract_item(Prototype.IronPlate, chest.position, quantity=2)
# count will be 2, items move to player inventory

# Extract using entity
count = extract_item(Prototype.IronPlate, chest, quantity=5)
# count will be 5, items move to player inventory
```

## Common Pitfalls

1. **Empty Inventories**
   - Attempting to extract from empty inventories will raise an exception
   - Always verify item existence before extraction

2. **Distance Limitations**
   - Player must be within range of the target entity
   - Move closer if extraction fails due to distance

## Best Practices

1. **Inventory Verification**
   Example - Safe smelting ore into plates

```python
# move to the position to place the entity
move_to(position)
furnace = place_entity(Prototype.StoneFurnace, position=position)
print(f"Placed the furnace to smelt plates at {furnace.position}")

# we also update the furnace variable by returning it from the function
# This ensures it doesnt get stale and the inventory updates are represented in the variable
furnace = insert_item(Prototype.Coal, furnace, quantity=5)  # Don't forget fuel
furnace = insert_item(Prototype.IronOre, furnace, quantity=10)

# 3. Wait for smelting (with safety timeout)
for _ in range(30):  # Maximum 30 seconds wait
    if inspect_inventory(furnace)[Prototype.IronPlate] >= 10:
        break
    sleep(1)
else:
    raise Exception("Smelting timeout - check fuel and inputs")

# final check for the inventory of furnace
iron_plates_in_furnace = inspect_inventory(furnace)[Prototype.IronPlate]
assert iron_plates_in_furnace>=10, "Not enough iron plates in furnace"
print(f"Smelted 10 iron plates")
```
