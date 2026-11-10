# get_construction_status

## Overview

The `get_construction_status` tool reports your force's roboport networks, ghosts, entities marked for deconstruction and your last 10 blueprint placements, read from the game. The observation shows the same as a Construction section once any of these exist.

## Function Signature

```python
def get_construction_status() -> dict
```

### Returns

A dict with `networks` (per roboport network: roboports, those with no or low power, construction and logistic robots and how many are idle, the 10 most stored items), `ghosts` and `deconstruction` (counts), `ghosts_waiting` and `deconstruction_waiting` (groups of `reason`, `count` and the nearest `x`, `y`, for the 200 nearest you that robots can't work on) and `placements` (`ghosts_placed`, `built`, `ghosts_waiting` per placement).

## Key Behaviors

The reasons are: not in the construction area of any roboport; no construction robots in the roboport network; no ITEM in the roboport network's storage.
