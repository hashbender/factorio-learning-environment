# get_resource_patch

The `get_resource_patch` tool analyzes and returns information about resource patches in Factorio, including their size, boundaries, and total available resources. This tool is essential for planning mining operations and factory layouts.

## Core Functionality

The tool provides:

- Total resource amount in a patch
- Bounding box coordinates of the patch
- Support for all resource types (ores, water, trees)

## Basic Usage

```python
# Get information about a resource patch
patch = get_resource_patch(
    resource=Resource.X,     # Resource type to find
    position=Position(x,y),  # Center position to search
    radius=30               # Search radius (default: 30)
)
```

### Parameters

1. `resource`: Resource - Type of resource to analyze (e.g., Resource.Coal, Resource.Water)
2. `position`: Position - Center point to search around
3. `radius`: int - Search radius in tiles (default: 30)

### Return Value

Returns a ResourcePatch object containing:

```python
ResourcePatch(
    name=str,              # Resource name
    size=int,              # Total resource amount (crude oil: per second, see below)
    bounding_box=BoundingBox(
        left_top=Position(x,y),
        right_bottom=Position(x,y),
        left_bottom=Position(x,y),
        right_top=Position(x,y)
    ),
    wells=None             # Crude oil only: number of wells in the field
)
```

When there is none of the resource within `radius` tiles of `position` (for water, no water tiles; for wood, no trees), it returns `None` instead of a ResourcePatch.

## Resource Types

### 1. Ore Resources

```python
# Check iron ore patch
iron_patch = get_resource_patch(
    Resource.IronOre,
    position=Position(x=0, y=0)
)
print(f"Found {iron_patch.size} iron ore")
```

### 2. Water Resources

```python
# Check water area
water_patch = get_resource_patch(
    Resource.Water,
    position=Position(x=0, y=0)
)
print(f"Water area contains {water_patch.size} tiles")
```

### 3. Crude Oil

Crude oil comes from separate wells, and each well's amount is a yield (300000 = 100%,
10 crude oil per second for a pumpjack in Factorio 2.0). For crude oil the patch is the
field (wells within 30 tiles of each other), `size` is the crude oil per second that one
pumpjack on every well gives at base mining speed, and `wells` is the number of wells.

```python
oil_field = get_resource_patch(Resource.CrudeOil, position=Position(x=0, y=0))
print(f"{oil_field.wells} wells, {oil_field.size} crude oil per second")
```
