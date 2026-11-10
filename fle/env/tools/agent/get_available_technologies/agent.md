# get_available_technologies

## Overview

The `get_available_technologies` tool lists the technologies your force can research right now, as the game's technology screen shows them: enabled, not yet researched, and with every prerequisite researched.

## Function Signature

```python
def get_available_technologies() -> List[AvailableTechnology]
```

### Returns

A list sorted by technology name. Each entry has:
- `name`: the technology name, usable with `set_research` and `queue_research`
- `ingredients`: the science packs one research unit needs (name and count)
- `unit_count`: the number of research units
- `unit_time`: the seconds one unit takes in a lab with research speed 1 (before research speed bonuses)
- `trigger`: for a trigger technology, the game action that completes it (e.g. `"craft 50 iron-plate"`), otherwise `None`. Trigger technologies have no units and can't be researched in labs.

## Usage Example

```python
for tech in get_available_technologies():
    if tech.trigger:
        print(f"{tech.name}: completed by: {tech.trigger}")
    else:
        packs = ", ".join(f"{i.count} {i.name}" for i in tech.ingredients)
        print(f"{tech.name}: {tech.unit_count} units x ({packs}), {tech.unit_time}s per unit")
```

## Key Behaviors

- A technology whose prerequisites are not all researched is not listed, even if they are in the research queue
- The total packs of one kind for a technology is the per-unit count times `unit_count`
- The list is read from the game each call and doesn't change the research queue
