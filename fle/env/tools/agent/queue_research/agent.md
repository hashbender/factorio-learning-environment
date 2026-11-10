# queue_research

## Overview

The `queue_research` tool appends technologies to the research queue of the player's force. In Factorio 2.0 the research queue is always on: it holds up to 7 technologies, current research first, and when the current research finishes the next technology in the queue starts.

`set_research(tech)` sets the current research; `queue_research([techs])` adds technologies behind it.

## Function Signature

```python
def queue_research(technologies: Union[Technology, str, List[Union[Technology, str]]]) -> List[str]
```

### Parameters

- `technologies`: A Technology enum value or technology name (e.g. `"automation-2"`), or a list of them, queued in the order given

### Returns

- The research queue after the call, as technology names, current research first

## Usage Example

```python
queue = queue_research([Technology.Automation, Technology.Logistics])
print(queue)  # ['automation', 'logistics']

# An empty list leaves the queue unchanged and returns it
print(queue_research([]))
```

## Key Behaviors

- Technologies are appended in the order given
- A technology that is already queued keeps its place
- A technology can be queued when each of its prerequisites is researched or earlier in the queue
- All or nothing: if one technology can't be queued, the queue is left as it was and an exception is raised

## Error Cases

The tool raises an exception, and queues nothing, when a technology:

- doesn't exist (the message lists the closest technology names)
- is already researched
- is not enabled
- is a trigger technology (completed by a game action instead of labs; the message names the action)
- has a prerequisite that is neither researched nor queued

or when the research queue is full (7 technologies).

Example error messages:

```python
"Cannot queue automation-2. Missing prerequisites (not researched or queued): automation"
"Cannot queue oil-processing. It is a trigger technology, completed by a game action instead of labs: mine crude-oil"
"Cannot queue logistics-2. The research queue is full (7 technologies)"
```
