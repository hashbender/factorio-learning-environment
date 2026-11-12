# set_research

## Overview

The `set_research` tool enables setting the current research technology for the player's force in Factorio. It manages research prerequisites, validates technology availability, and provides information about required research ingredients.

## Function Signature

```python
def set_research(technology: Union[Technology, str]) -> List[Ingredient]
```

### Parameters

- `technology`: A Technology enum value, or the technology's name as a string (e.g. `"automation-2"`). `Technology` has a member for every Factorio 2.0 base-game technology.

### Returns

- Returns a list of `Ingredient` objects containing the required science packs and their quantities
- Each `Ingredient` object has:
  - `name`: Name of the required science pack
  - `count`: Number of science packs needed
  - `type`: Type of the ingredient (usually "item" for science packs)

## Usage Example

```python
# Set research to Automation technology
ingredients = set_research(Technology.Automation)

# Check required ingredients
for ingredient in ingredients:
    print(f"Need {ingredient.count} {ingredient.name}")
```

## Key Behaviors

- Cancels the current research once the checks below pass (the game keeps its progress)
- Makes the technology the current research; other technologies in the research queue keep their order behind it. A technology that is already in the queue moves to the front
- A refused or failed call (an error) leaves the current research and the research queue unchanged
- Validates technology prerequisites
- Returns detailed ingredient requirements for the research

## Validation Checks

The tool performs several validation checks before starting research:

1. Verifies the technology exists
2. Confirms the technology isn't already researched
3. Checks if the technology is enabled
4. Checks the technology is not a trigger technology (see below)
5. Validates all prerequisites are researched

## Error Cases

The tool will raise exceptions in the following situations:

- Technology doesn't exist (the message lists the closest technology names)
- Technology is already researched
- Technology is not enabled
- Technology is a trigger technology (the message names the game action that completes it)
- Missing prerequisites
- Failed to start research

Example error messages:

```python
"Cannot start research for automation-2. Missing prerequisites: automation"
"Technology logistics-2 is not enabled"
```

## Trigger Technologies

In Factorio 2.0 some technologies are not researched in labs. They have no science-pack cost and are completed when the game action shown is done:

- `steam-power`: craft 50 iron plates
- `electronics`: craft 10 copper plates
- `automation-science-pack`: craft a lab
- `steel-axe`: craft 50 steel plates
- `oil-processing`: mine crude oil
- `uranium-processing`: mine uranium ore
- `space-science-pack`: send a satellite to orbit

`set_research` raises for a trigger technology, and the current research is left unchanged:

```python
"Cannot start research for steam-power. It is a trigger technology, completed by a game action instead of labs: craft 50 iron-plate"
```

## Requirements

- The technology must be valid and available
- All prerequisites must be researched
