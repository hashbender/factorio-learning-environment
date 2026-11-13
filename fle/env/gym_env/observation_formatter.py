import pickle
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from fle.commons.constants import REWARD_OVERRIDE_KEY
from fle.env.gym_env.observation import CLIFF_LIMIT, CLIFF_RADIUS, Observation


# Power network fields: powers in W, energies in J
POWER_KEYS = {"production", "consumption", "demand", "generator_max"}
ENERGY_KEYS = {"accumulator_charge", "accumulator_capacity"}
# At most this many electric networks are listed in the Power section
POWER_NETWORKS_SHOWN = 10
# Machine Status section. Every machine that is not working is listed with its
# position and the game's reason. Lines whose machines are all working are
# counts only, and at most MACHINE_LINES_SHOWN of them are listed (the rest are
# counted). The whole section stays within MACHINE_SECTION_CHARS: lines are
# kept whole, and a last line counts the machines on the lines left out.
MACHINE_LINES_SHOWN = 20
MACHINE_SECTION_CHARS = 10000
# r22: at most this many chars per line (lower when the lines together would not fit the section): longer position
# lists end with "+N more positions"
MACHINE_LINE_CHARS = 1200
# r22: ... but never below this many: past that, lines are left out whole (and counted) as before
MACHINE_LINE_MIN_CHARS = 300
# r22: target positions inside a status detail (serialize.lua detail_pos "(12.5, -3.5)"), removed from the state so
# that machines in the same state are one group: " at (x, y)", " (x, y) to (x, y)", then any other " (x, y)"
_MACHINE_DETAIL_POS = r"\(-?\d+(?:\.\d+)?, -?\d+(?:\.\d+)?\)"
MACHINE_DETAIL_POS_RES = [
    re.compile(r" at " + _MACHINE_DETAIL_POS),
    re.compile(r" " + _MACHINE_DETAIL_POS + r" to " + _MACHINE_DETAIL_POS),
    re.compile(r" " + _MACHINE_DETAIL_POS),
]
# Entity types listed in the Machine Status section
MACHINE_TYPES = {
    "assembling-machine",
    "rocket-silo",
    "furnace",
    "lab",
    "mining-drill",
    "inserter",
}
# States counted without positions
MACHINE_WORKING_STATES = {"working", "normal"}


def _si(value: float, unit: str) -> str:
    value = float(value)
    for factor, prefix in ((1e9, "G"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= factor:
            scaled = value / factor
            text = f"{scaled:.1f}".rstrip("0").rstrip(".")
            return f"{text} {prefix}{unit}"
    return f"{value:.0f} {unit}"


def format_watts(value: float) -> str:
    """900000 -> "900 kW"."""
    return _si(value, "W")


def format_joules(value: float) -> str:
    """5000000 -> "5 MJ"."""
    return _si(value, "J")


def format_network(n: Dict[str, Any]) -> str:
    """One electric network summary on one line (the power pole GUI's numbers)."""
    parts = [
        f"production {format_watts(n.get('production') or 0)}"
        f" (generators max {format_watts(n.get('generator_max') or 0)})",
        f"consumption {format_watts(n.get('consumption') or 0)}",
        f"demand {format_watts(n.get('demand') or 0)}",
    ]
    satisfaction = n.get("satisfaction")
    parts.append(
        f"satisfaction {satisfaction:.0%}"
        if isinstance(satisfaction, (int, float))
        else "satisfaction - (no demand)"
    )
    parts.append(
        f"consumers {n.get('consumers') or 0}"
        f" (low power {n.get('low_power') or 0}, no power {n.get('no_power') or 0})"
    )
    if n.get("accumulators"):
        parts.append(
            f"accumulators {n['accumulators']}:"
            f" {format_joules(n.get('accumulator_charge') or 0)}"
            f" / {format_joules(n.get('accumulator_capacity') or 0)}"
        )
    counts = f"poles {n.get('poles') or 0}, generators {n.get('generators') or 0}"
    return ", ".join(parts) + ", " + counts


@dataclass
class FormattedObservation:
    """Container for formatted observation strings"""

    inventory_str: str
    """Formatted string showing current inventory contents.
    Example:
    ### Inventory
    - iron-ore: 100
    - coal: 50
    - transport-belt: 10
    Items are sorted by quantity in descending order."""

    entities_str: str
    """Formatted string showing entities on the map grouped by type.
    Example:
    ### Entities
    - burner-mining-drill: 2
    - transport-belt: 5
    - inserter: 3
    Entities are grouped and counted by their type."""

    flows_str: str
    """Formatted string showing current production flow rates.
    Example:
    ### Production Flows
    #### Inputs
    - coal: 1.50/s
    #### Outputs
    - iron-ore: 0.75/s
    Shows both input consumption and output production rates per second."""

    task_str: str
    """Formatted string showing task verification status and criteria.
    Example:
    ### Task Status
    ⏳ IN PROGRESS

    **Message:** Need more iron plates

    **Criteria:**
    - ✅ Place mining drill
    - ❌ Produce 100 iron plates
    Empty string if no task is being tracked."""

    task_info_str: str
    """Formatted string showing task information and objectives.
    Example:
    ### Task Information
    **Goal:** Create automatic iron ore factory
    **Agent Instructions:** You are the mining specialist
    **Task Key:** iron_ore_automation"""

    messages_str: str
    """Formatted string showing messages received from other agents.
    Example:
    ### Messages
    - **[Agent 1]**: Need more iron plates
    - **[Agent 2]**: I'll help with that
    Empty string if no messages were received."""

    functions_str: str
    """Formatted string showing available functions with their signatures and docstrings.
    Example:
    ### Available Functions
    ```python
    def find_idle_furnaces(entities: List[Entity]) -> List[Entity]
      \"\"\"Find all furnaces that are not currently working.\"\"\"
    ```
    Shows function names, parameter types, return types, and docstrings."""

    game_info_str: str
    """Formatted string showing game timing information.
    Example:
    ### Game Info
    - Elapsed Time: 1:00:00
    - Ticks: 3600
    Shows elapsed time in hours:minutes:seconds format and current game tick count."""

    raw_text_str: str
    """Formatted string showing the raw text output from the last action.
    Example:
    ### Raw Output
    ```
    Successfully placed mining drill at position (10, 5)
    Current iron ore production: 0.75/s
    ```
    Shows the direct output from the executed code."""

    character_positions_str: str
    """Formatted string showing character positions for all agents.
    Example:
    ### Character Positions
    - Agent 0: (10.5, 5.0)
    - Agent 1: (15.0, 8.5)
    Shows x, y coordinates for each agent's character."""

    cliffs_str: str
    """Formatted string showing the cliffs near the character, nearest first.
    Example:
    ### Cliffs
    The nearest cliffs within 40 tiles of you (up to 25, nearest first): (12, -30), (14, -30)
    Empty when the cliffs are unknown."""

    resources_str: str = ""
    """Formatted string listing the resource patches near the factory.
    Example:
    ### Resources
    Resource patches with a tile within 100 tiles of the area x -40..60,
    y -30..50 (your buildings and you); whole patches (up to 1000 tiles from
    you), amounts from the game:
    - iron-ore: 2 patches, 1,804,213 total
      - 1,512,000 on 1,240 tiles, x -120.5..-80.5, y 10.5..52.5
      - 292,213 on 310 tiles, x 70.5..90.5, y -60.5..-44.5
    Empty when the patches are unknown."""

    power_str: str = ""
    """Formatted string summarising each electric network (power pole GUI).
    Example:
    ### Power
    - network 1: production 900 kW (generators max 900 kW), consumption 900 kW,
      demand 1.2 MW, satisfaction 75%, consumers 4 (low power 4, no power 0), ...
    Empty when the networks are unknown."""

    construction_str: str = ""
    """Formatted string summarising roboport networks, ghosts, deconstruction
    orders and blueprint placements (get_construction_status).
    Example:
    ### Construction
    - roboport network 2: 1 roboports (0 without power), construction robots 10 (10 idle), ...
    - ghosts: 6; not being built: 6 no iron-gear-wheel in the roboport network's storage (first at (40.5, 20.5))
    Empty when there are none."""

    raw_str: str = ""
    """Complete formatted observation combining all components.
    Example:
    ### Inventory
    - iron-ore: 100
    - coal: 50

    ### Entities
    - burner-mining-drill: 2
    - transport-belt: 5

    ### Production Flows
    #### Inputs
    - coal: 1.50/s
    #### Outputs
    - iron-ore: 0.75/s

    ### Available Functions
    ```python
    def find_idle_furnaces(entities: List[Entity]) -> List[Entity]
      \"\"\"Find all furnaces that are not currently working.\"\"\"
    ```

    ### Game Info
    - Elapsed Time: 1:00:00
    - Ticks: 3600

    ### Character Positions
    - Agent 0: (10.5, 5.0)

    ### Task Status
    ⏳ IN PROGRESS

    **Message:** Need more iron plates

    **Criteria:**
    - ✅ Place mining drill
    - ❌ Produce 100 iron plates

    ### Messages
    - **[Agent 1]**: Need more iron plates
    - **[Agent 2]**: I'll help with that

    ### Raw Output
    ```
    Successfully placed mining drill at position (10, 5)
    Current iron ore production: 0.75/s
    ```"""


class BasicObservationFormatter:
    """Formats gym environment observations into helpful strings"""

    def __init__(
        self,
        include_inventory: bool = True,
        include_entities: bool = True,
        include_flows: bool = True,
        include_task: bool = True,
        include_messages: bool = True,
        include_functions: bool = True,
        include_state_changes: bool = True,
        include_raw_output: bool = True,
        include_research: bool = True,
        include_game_info: bool = True,
        include_character_positions: bool = True,
        include_cliffs: bool = True,
        include_power: bool = True,
        include_resources: bool = True,
        include_machine_status: bool = True,
        include_construction: bool = True,
    ):
        """Initialize the formatter with flags for which fields to include"""
        self.include_inventory = include_inventory
        self.include_entities = include_entities
        self.include_flows = include_flows
        self.include_task = include_task
        self.include_messages = include_messages
        self.include_functions = include_functions
        self.include_state_changes = include_state_changes
        self.include_raw_output = include_raw_output
        self.include_research = include_research
        self.include_game_info = include_game_info
        self.include_character_positions = include_character_positions
        self.include_cliffs = include_cliffs
        self.include_power = include_power
        self.include_resources = include_resources
        self.include_machine_status = include_machine_status
        self.include_construction = include_construction

    def _entities_section(self, entities: List[Any]) -> str:
        return self.format_entities(entities)

    @staticmethod
    def format_inventory(inventory: List[Dict[str, Any]]) -> str:
        """Format inventory information"""
        if not inventory:
            return "### Inventory\nEmpty"

        # Convert list of dicts to dict for easier sorting
        inventory_dict = {
            item["type"]: item["quantity"] for item in inventory if item["quantity"] > 0
        }

        # Sort items by quantity for consistent output
        sorted_items = sorted(inventory_dict.items(), key=lambda x: x[1], reverse=True)

        # Format each item
        item_strs = []
        for item_type, quantity in sorted_items:
            item_strs.append(f"- {item_type}: {quantity}")

        return "### Inventory\n" + "\n".join(item_strs)

    @staticmethod
    def format_entities(entities: List[Any]) -> str:
        """Format entity information"""
        if not entities:
            return "### Entities\nNone found"

        # Convert dicts to string representations for legacy parsing
        entities = [str(e) if isinstance(e, dict) else e for e in entities]

        def clean_entity_string(entity_str: str) -> str:
            """Clean and format an entity string for better readability"""
            # Remove class references and unnecessary information
            entity_str = entity_str.replace("class 'fle.env.entities.", "")
            entity_str = entity_str.replace("'>", "")

            # Split into key-value pairs, being careful with nested structures
            parts = []
            current_part = []
            bracket_level = 0
            quote_level = 0

            for char in entity_str:
                if char == "[":
                    bracket_level += 1
                elif char == "]":
                    bracket_level -= 1
                elif char == "'":
                    quote_level = 1 - quote_level
                elif char == "(":
                    bracket_level += 1
                elif char == ")":
                    bracket_level -= 1

                if char == " " and bracket_level == 0 and quote_level == 0:
                    if current_part:
                        parts.append("".join(current_part))
                        current_part = []
                else:
                    current_part.append(char)

            if current_part:
                parts.append("".join(current_part))

            # Process each part
            formatted_parts = []
            for part in parts:
                if "=" in part:
                    key, value = part.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # Clean up the value
                    if "Position" in value:
                        # Extract x and y coordinates
                        x_match = re.search(r"x=([\d.]+)", value)
                        y_match = re.search(r"y=([\d.]+)", value)
                        if x_match and y_match:
                            x = float(x_match.group(1))
                            y = float(y_match.group(1))
                            value = f"({x:.1f}, {y:.1f})"
                    elif "Dimensions" in value:
                        # Extract width and height
                        w_match = re.search(r"width=([\d.]+)", value)
                        h_match = re.search(r"height=([\d.]+)", value)
                        if w_match and h_match:
                            w = float(w_match.group(1))
                            h = float(h_match.group(1))
                            value = f"({w:.1f}, {h:.1f})"
                    elif "TileDimensions" in value:
                        # Extract tile width and height
                        w_match = re.search(r"tile_width=([\d.]+)", value)
                        h_match = re.search(r"tile_height=([\d.]+)", value)
                        if w_match and h_match:
                            w = float(w_match.group(1))
                            h = float(h_match.group(1))
                            value = f"({w:.1f}, {h:.1f})"
                    elif "Prototype" in value:
                        # Convert "<Prototype.Boiler: ...>" to "Prototype.Boiler"
                        proto_match = re.search(r"<Prototype\.([^:>]+)[:>]?", value)
                        if proto_match:
                            value = f"Prototype.{proto_match.group(1)}"
                        else:
                            # Fallback: use the part after 'Prototype.' if present
                            alt_match = re.search(r"Prototype\.([A-Za-z0-9_-]+)", value)
                            if alt_match:
                                value = f"Prototype.{alt_match.group(1)}"

                    # Format numbers consistently
                    if isinstance(value, str):
                        # Try to convert to float if it's a number
                        try:
                            num = float(value)
                            value = f"{num:.1f}"
                        except ValueError:
                            pass

                    # Remove any double commas
                    value = re.sub(r",\s*,", ",", value)

                    formatted_parts.append(f"{key}={value}")
                else:
                    formatted_parts.append(part)

            return ", ".join(formatted_parts)

        # Group entities by type
        entity_groups = {}
        name_pattern = re.compile(r"\bname\s*=\s*'?([A-Za-z0-9_-]+)'?")
        group_pattern = re.compile(r"^\s*([A-Za-z]+Group)\(")

        for entity_str in entities:
            # Extract entity type using regex (handles both quoted and unquoted values)
            type_match = None
            # Try to get name first
            n = name_pattern.search(entity_str)
            if n:
                type_match = n.group(1)
            # Fallback: recognise special group objects like PipeGroup(...)
            if not type_match:
                g = group_pattern.match(entity_str)
                if g:
                    type_match = g.group(1)  # e.g., PipeGroup, ElectricityGroup

            if type_match:
                if type_match not in entity_groups:
                    entity_groups[type_match] = []
                # Clean the entity string before adding to group
                cleaned_str = clean_entity_string(entity_str)
                entity_groups[type_match].append(cleaned_str)
            else:
                # Skip entities we cannot categorise but keep a console warning for debugging
                print(
                    "[ObservationFormatter] Unable to determine type for entity:",
                    entity_str,
                )

        # Format each entity group
        group_strs = []
        for entity_type, group in sorted(entity_groups.items()):
            count = len(group)
            group_str = f"- {entity_type}: {count}"

            # Add details for each entity in the group
            if group:
                group_str += "\n" + "\n".join(f"  - {entity}" for entity in group)

            group_strs.append(group_str)

        return "### Entities\n" + "\n".join(group_strs)

    @staticmethod
    def format_flows(flows: Dict[str, Any]) -> str:
        """Format production flow information"""
        if not flows or not any(flows.values()):
            return "### Production Flows\nNone"

        flow_str = "### Production Flows (for *entire* previous step)\n"

        # Build harvested lookup to subtract from production
        harvested_by_type = {}
        for item in flows.get("harvested", []):
            harvested_by_type[item["type"]] = item.get("amount", 0)

        # Format input flows
        if flows.get("input"):
            flow_str += "#### Inputs\n"
            for item in flows["input"]:
                if item["rate"] > 0:
                    flow_str += f"- {item['type']}: {item['rate']:.2f}\n"

        # Format output flows (subtract harvested since production includes both automated and harvested)
        if flows.get("output"):
            if flows.get("input"):
                flow_str += "\n"
            flow_str += "#### Outputs\n"
            for item in flows["output"]:
                # Subtract harvested amount from production
                harvested_amount = harvested_by_type.get(item["type"], 0)
                adjusted_rate = item["rate"] - harvested_amount
                if adjusted_rate > 0:
                    flow_str += f"- {item['type']}: {adjusted_rate:.2f}\n"

        # Format crafted items
        if flows.get("crafted"):
            if flows.get("input") or flows.get("output"):
                flow_str += "\n"
            flow_str += "#### Crafted Items\n"
            for item in flows["crafted"]:
                # Crafted items have structure: {"crafted_count": N, "inputs": {...}, "outputs": {...}}
                # Display the outputs (what was crafted) with the count
                crafted_count = item.get("crafted_count", 1)
                outputs = item.get("outputs", {})
                if outputs:
                    for output_name, output_amount in outputs.items():
                        flow_str += f"- {output_name}: {output_amount} (crafted {crafted_count}x)\n"
                else:
                    # Fallback for legacy format with "type" field
                    item_name = item.get("type", "unknown")
                    count = item.get("count", 1)
                    if item_name != "unknown":
                        flow_str += f"- {item_name}: {count}\n"

        # Format harvested items
        if flows.get("harvested"):
            if flows.get("input") or flows.get("output") or flows.get("crafted"):
                flow_str += "\n"
            flow_str += "#### Harvested Items\n"
            for item in flows["harvested"]:
                if item["amount"] > 0:
                    flow_str += f"- {item['type']}: {item['amount']:.2f}\n"

        # Format price list
        if flows.get("price_list"):
            if any(flows.get(k) for k in ["input", "output", "crafted", "harvested"]):
                flow_str += "\n"
            flow_str += "#### Price List\n"
            for item in flows["price_list"]:
                flow_str += f"- {item['type']}: {item['price']:.2f}\n"

        # Format static items
        if flows.get("static_items"):
            if any(
                flows.get(k)
                for k in ["input", "output", "crafted", "harvested", "price_list"]
            ):
                flow_str += "\n"
            flow_str += "#### Static Items\n"
            for item in flows["static_items"]:
                flow_str += f"- {item['type']}: {item['value']:.2f}\n"

        return flow_str

    @staticmethod
    def format_flows_compact(flows: Dict[str, Any]) -> str:
        """Format production flows into compact sub-bullets.

        Args:
            flows: Dict with keys 'input', 'output', 'crafted', 'harvested'
                  - input: list of {"type": str, "rate": float} (consumed items)
                  - output: list of {"type": str, "rate": float} (produced items)
                  - crafted: list of crafted item dicts
                  - harvested: list of {"type": str, "amount": float}

        Returns:
            Formatted string with sub-bullets for each flow type
        """
        lines = []

        # Build harvested lookup to subtract from production
        harvested_by_type = {}
        for item in flows.get("harvested", []):
            harvested_by_type[item["type"]] = item.get("amount", 0)

        # Consumed (input)
        consumed = flows.get("input", [])
        if consumed:
            items = ", ".join(
                f"{item['type']}: {item['rate']:.1f}"
                for item in consumed
                if item.get("rate", 0) > 0
            )
            lines.append(f"  - Consumed: {items}" if items else "  - Consumed: none")
        else:
            lines.append("  - Consumed: none")

        # Produced (output) - subtract harvested since production includes both automated and harvested
        produced = flows.get("output", [])
        if produced:
            adjusted_items = []
            for item in produced:
                harvested_amount = harvested_by_type.get(item["type"], 0)
                adjusted_rate = item.get("rate", 0) - harvested_amount
                if adjusted_rate > 0:
                    adjusted_items.append(f"{item['type']}: {adjusted_rate:.1f}")
            items = ", ".join(adjusted_items)
            lines.append(f"  - Produced: {items}" if items else "  - Produced: none")
        else:
            lines.append("  - Produced: none")

        # Crafted - aggregate by item type
        crafted = flows.get("crafted", [])
        if crafted:
            crafted_totals: Dict[str, float] = {}
            for item in crafted:
                count = item.get("crafted_count", 1)
                outputs = item.get("outputs", {})
                for name, amount in outputs.items():
                    # amount is the output per craft, count is number of crafts
                    total_produced = amount * count
                    crafted_totals[name] = crafted_totals.get(name, 0) + total_produced
            if crafted_totals:
                # Sort by total amount descending for readability
                sorted_items = sorted(crafted_totals.items(), key=lambda x: -x[1])
                items = ", ".join(
                    f"{name}: {int(total)}" for name, total in sorted_items
                )
                lines.append(f"Crafted: {items}")
            else:
                lines.append("Crafted: none")
        else:
            lines.append("Crafted: none")

        # Harvested
        harvested = flows.get("harvested", [])
        if harvested:
            items = ", ".join(
                f"{item['type']}: {item['amount']:.1f}"
                for item in harvested
                if item.get("amount", 0) > 0
            )
            lines.append(f"  - Harvested: {items}" if items else "  - Harvested: none")
        else:
            lines.append("  - Harvested: none")

        return "\n".join(lines)

    @staticmethod
    def format_research(research: Dict[str, Any]) -> str:
        """Format research state information"""
        if not research:
            return "### Research\nNone"

        research_str = "### Research\n"

        # Format current research
        if research.get("current_research"):
            research_str += f"#### Current Research\n- {research['current_research']}: {research['research_progress'] * 100:.1f}%\n"

        # Format research queue
        if research.get("research_queue"):
            if research.get("current_research"):
                research_str += "\n"
            research_str += "#### Research Queue\n"
            for tech in research["research_queue"]:
                research_str += f"- {tech}\n"

        # Format technologies
        techs = research.get("technologies")
        if techs:
            # Accept both dict and list
            if isinstance(techs, list):
                # Convert list to dict using 'name' as key
                techs = {t["name"]: t for t in techs if "name" in t}
            if research.get("current_research") or research.get("research_queue"):
                research_str += "\n"
            research_str += "#### Technologies\n"
            for name, tech in techs.items():
                status = "✅" if tech.get("researched") else "⏳"
                enabled = "🔓" if tech.get("enabled") else "🔒"
                research_str += (
                    f"- {status} {enabled} {name} (Level {tech.get('level', 0)})\n"
                )
                if tech.get("prerequisites"):
                    research_str += (
                        f"  Prerequisites: {', '.join(tech['prerequisites'])}\n"
                    )
                if tech.get("ingredients"):
                    # Handle both list of dicts and dict formats
                    if isinstance(tech["ingredients"], list):
                        ingredients = ", ".join(
                            f"{ing.get('name', ing.get('item', ''))} x{ing.get('amount', ing.get('value', 0))}"
                            for ing in tech["ingredients"]
                        )
                        research_str += f"  Ingredients: {ingredients}\n"
                    else:
                        research_str += f"  Ingredients: {', '.join(f'{item} x{amount}' for item, amount in tech['ingredients'].items())}\n"
                if tech.get("research_unit_count", 0) > 0:
                    research_str += f"  Research Units: {tech['research_unit_count']} (Energy: {tech.get('research_unit_energy', 0):.1f})\n"

        return research_str

    @staticmethod
    def format_game_info(
        game_info: Dict[str, Any],
        score: float = 0.0,
        automated_score: float = 0.0,
    ) -> str:
        """Format game timing and score information"""
        if not game_info:
            return "### Game Info\nNo game information available"

        info_str = "### Game Info\n"

        # Add elapsed time information in H:M:S format
        if "time" in game_info:
            total_seconds = int(game_info["time"])
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            info_str += f"- Elapsed Time: {hours:d}:{minutes:02d}:{seconds:02d}\n"

        # Add tick information
        if "tick" in game_info:
            info_str += f"- Ticks: {game_info['tick']}\n"

        # Add score information
        info_str += f"- Production Score: {score:.1f}\n"
        info_str += f"- Automated Score: {automated_score:.1f}\n"

        return info_str

    @staticmethod
    def format_task(task: Optional[Dict[str, Any]]) -> str:
        """Format task verification information"""
        if not task:
            return ""

        status = "✅ SUCCESS" if task["success"] else "⏳ IN PROGRESS"
        task_str = f"### Task Status\n{status}\n"

        if task.get("message"):
            task_str += f"\n**Message:** {task['message']}\n"

        if task.get("meta"):
            task_str += "\n**Task Details:**\n"
            for meta_item in task["meta"]:
                if meta_item["key"] == REWARD_OVERRIDE_KEY:
                    continue
                task_str += f"- {meta_item['key']}: {meta_item['value']}\n"

        return task_str

    @staticmethod
    def format_task_info(task_info: Optional[Dict[str, Any]]) -> str:
        """Format task information"""
        if not task_info:
            return ""

        info_str = "### Task Information\n"

        if task_info.get("goal_description"):
            info_str += f"**Goal:** {task_info['goal_description']}\n"

        if task_info.get("agent_instructions"):
            info_str += f"**Agent Instructions:** {task_info['agent_instructions']}\n"

        if task_info.get("task_key"):
            info_str += f"**Task Key:** {task_info['task_key']}\n"

        if task_info.get("trajectory_length"):
            info_str += f"**Trajectory Length:** {task_info['trajectory_length']}\n"

        return info_str

    @staticmethod
    def format_messages(
        messages: List[Dict[str, Any]], last_timestamp: float = 0.0
    ) -> str:
        """Format messages from other agents"""
        if not messages:
            return ""

        # Filter messages newer than last timestamp
        new_messages = [msg for msg in messages if msg["timestamp"] > last_timestamp]

        if not new_messages:
            return ""

        # Format messages
        message_strs = ["### Messages"]
        for msg in new_messages:
            sender_info = (
                f"Agent {msg['sender']}" if msg["sender"] != "-1" else "Leader"
            )
            message_strs.append(f"- **[{sender_info}]**: {msg['content']}")

        return "\n".join(message_strs)

    @staticmethod
    def format_functions(serialized_functions: List[Dict[str, Any]]) -> str:
        """Format serialized functions into readable descriptions"""
        if not serialized_functions:
            return ""

        # Unpickle and format each function
        function_strs = ["### Available Functions"]
        for func_data in serialized_functions:
            try:
                # Unpickle the function
                pickled_data = bytes.fromhex(func_data["pickled_function"])
                func = pickle.loads(pickled_data)

                # Get formatted string representation
                function_strs.append(f"\n```python\n{func}\n```")
            except Exception as e:
                function_strs.append(
                    f"\n- {func_data['name']}: [Error unpickling function: {str(e)}]"
                )

        return "\n".join(function_strs)

    @staticmethod
    def format_raw_text(raw_text: str) -> str:
        """Format raw text output from the last action"""
        if not raw_text or raw_text.strip() == "":
            return ""

        return f"### Raw Output\n```\n{raw_text.strip()}\n```"

    @staticmethod
    def format_character_positions(character_positions: List[Dict[str, Any]]) -> str:
        """Format character positions for all agents.

        Args:
            character_positions: List of dicts with 'agent_idx', 'x', 'y' keys

        Returns:
            Formatted string showing each agent's position
        """
        if not character_positions:
            return "### Character Positions\nNo characters"

        lines = ["### Character Positions"]
        for pos in character_positions:
            agent_idx = pos.get("agent_idx", 0)
            x = pos.get("x", 0.0)
            y = pos.get("y", 0.0)
            lines.append(f"- Agent {agent_idx}: ({x:.1f}, {y:.1f})")

        return "\n".join(lines)

    @staticmethod
    def format_cliffs(cliffs: Optional[List[Dict[str, Any]]]) -> str:
        """Format the cliffs near the character, nearest first.

        Args:
            cliffs: List of dicts with 'x', 'y' keys, or None if unknown

        Returns:
            Formatted string, or "" when the cliffs are unknown
        """
        if cliffs is None:
            return ""
        if not cliffs:
            return f"### Cliffs\nNone within {CLIFF_RADIUS} tiles of you."

        def number(v) -> str:
            f = float(v)
            return str(int(f)) if f == int(f) else f"{f:g}"

        points = ", ".join(f"({number(c['x'])}, {number(c['y'])})" for c in cliffs)
        return (
            f"### Cliffs\nThe nearest cliffs within {CLIFF_RADIUS} tiles of you "
            f"(up to {CLIFF_LIMIT}, nearest first): {points}"
        )

    @staticmethod
    def format_power(networks: Optional[List[Dict[str, Any]]]) -> str:
        """Format the electric network summaries, one line per network.

        Args:
            networks: List of network summary dicts (get_power_networks), or None
                if unknown

        Returns:
            Formatted string, or "" when the networks are unknown
        """
        if networks is None:
            return ""
        if not networks:
            return "### Power\nNo electric networks."
        # the biggest networks first; the rest are counted
        ordered = sorted(
            networks, key=lambda n: (-(n.get("poles") or 0), n.get("id") or 0)
        )
        lines = ["### Power"]
        for n in ordered[:POWER_NETWORKS_SHOWN]:
            lines.append(f"- network {n.get('id')}: {format_network(n)}")
        more = len(ordered) - POWER_NETWORKS_SHOWN
        if more > 0:
            lines.append(f"- ({more} more networks)")
        return "\n".join(lines)

    @staticmethod
    def format_resources(resources: Optional[Dict[str, Any]]) -> str:
        """Format the resource patches near the factory (get_resource_reserves).

        Args:
            resources: The get_resource_reserves result, or None if unknown

        Returns:
            Formatted string, or "" when the patches are unknown
        """
        if resources is None:
            return ""

        def num(v) -> str:
            v = float(v)
            return f"{v:g}" if v != int(v) else str(int(v))

        def amount(v) -> str:
            return f"{int(round(float(v))):,}"

        area = resources.get("area") or {}
        margin = num(resources.get("margin") or 0)
        radius = num(resources.get("radius") or 0)
        if area:
            what = "your buildings and you" if resources.get("buildings") else "you"
            where = (
                f"of the area x {num(area['x1'])}..{num(area['x2'])}, "
                f"y {num(area['y1'])}..{num(area['y2'])} ({what})"
            )
        else:
            where = "of you"
        lines = [
            "### Resources",
            f"Resource patches with a tile within {margin} tiles {where}; "
            f"whole patches (up to {radius} tiles from you), amounts from the game:",
        ]
        patches = list(resources.get("patches") or [])
        if not patches:
            lines.append("- none")
        by_name: Dict[str, List[Dict[str, Any]]] = {}
        for p in patches:
            by_name.setdefault(str(p.get("name", "?")), []).append(p)
        for name in sorted(by_name):
            group = sorted(by_name[name], key=lambda p: -float(p.get("amount") or 0))
            total = sum(float(p.get("amount") or 0) for p in group)
            infinite = any(p.get("infinite") for p in group)
            if infinite:
                head = f"- {name}: {len(group)} field{'s' if len(group) > 1 else ''}"
            else:
                head = (
                    f"- {name}: {len(group)} patch{'es' if len(group) > 1 else ''}, "
                    f"{amount(total)} total"
                )
            lines.append(head)
            for p in group:
                box = (
                    f"x {num(p['x1'])}..{num(p['x2'])}, y {num(p['y1'])}..{num(p['y2'])}"
                    if all(k in p for k in ("x1", "y1", "x2", "y2"))
                    else "area unknown"
                )
                if infinite:
                    normal = float(p.get("normal") or 0)
                    tiles = int(p.get("tiles") or 0)
                    text = f"{tiles} well{'s' if tiles != 1 else ''}"
                    if normal > 0:
                        text += (
                            f", yield {float(p.get('amount') or 0) / normal:.0%} total"
                        )
                    text += f" (amount {amount(p.get('amount') or 0)}), {box}"
                else:
                    text = f"{amount(p.get('amount') or 0)} on {int(p.get('tiles') or 0):,} tiles, {box}"
                if p.get("clipped"):
                    text += f" (continues past {radius} tiles from you; counted up to there)"
                lines.append(f"  - {text}")
        if resources.get("truncated"):
            lines.append("- (search limit reached: patches after these were not read)")
        return "\n".join(lines)

    @staticmethod
    def format_machine_status(entities: List[Any]) -> str:
        """One line per machine type and recipe (inserters: per inserter type):
        how many machines are in each state. A state is the status detail (the
        game's reason) when there is one, else the status name. Every state
        other than working ends with "at" and the positions of its machines
        (entity_compact.positions_text); working machines are a count. Counts,
        the game's reasons and positions only, sorted by name.

        Lines whose machines are all working: at most MACHINE_LINES_SHOWN, the
        rest counted. The section stays within MACHINE_SECTION_CHARS: lines are
        kept whole and the last line counts the machines on the lines left out.

        r22: the state leaves out the target positions in the detail (MACHINE_DETAIL_POS_RES),
        so "waiting for items from assembling-machine-1 at (12.5, -3.5)" and "... at (15.5, -3.5)"
        are one state. A line is at most MACHINE_LINE_CHARS (less when the lines together would
        not fit): the longest position lists end with "+N more positions", then the smallest
        non-working states are counted ("N more machines in M other states").

        Example:
        ### Machine Status
        - assembling-machine-1 [iron-gear-wheel]: 3 (2 working, 1 missing iron-plate (0 of 1 per craft) at (7.5, 1.5))
        """
        from fle.env.gym_env.entity_compact import positions_text

        def attr(obj: Any, key: str) -> Any:
            if isinstance(obj, dict):
                return obj.get(key, obj.get("_" + key))
            return getattr(obj, key, None)

        def position(e: Any) -> Optional[Tuple[float, float]]:
            pos = attr(e, "position")
            x, y = attr(pos, "x"), attr(pos, "y")
            try:
                return (float(x), float(y))
            except (TypeError, ValueError):
                return None

        groups: Dict[str, Dict[str, List[Optional[Tuple[float, float]]]]] = {}
        for e in entities or []:
            if not isinstance(e, dict):
                continue
            etype = attr(e, "type")
            if etype not in MACHINE_TYPES:
                continue
            name = str(attr(e, "name") or "?")
            if etype in ("assembling-machine", "rocket-silo"):
                recipe = attr(e, "recipe")
                recipe_name = attr(recipe, "name") if recipe else None
                if recipe_name is None and isinstance(recipe, str):
                    recipe_name = recipe
                name += f" [{recipe_name or 'no recipe'}]"
            status = attr(e, "status")
            status = str(getattr(status, "value", status) or "unknown")
            state = attr(e, "status_detail") or status.replace("_", " ")
            # r22: without the target positions (the machine's own position is listed after "at")
            for rx in MACHINE_DETAIL_POS_RES:
                state = rx.sub("", str(state))
            state = state or status.replace("_", " ")
            groups.setdefault(name, {}).setdefault(state, []).append(position(e))
        if not groups:
            return ""

        def where_text(group: List[Optional[Tuple[float, float]]], k: int) -> str:
            # r22: the first k positions (k >= 1), then "+N more positions" for the rest
            placed = sorted(p for p in group if p is not None)
            where = positions_text(placed[:k])
            if 0 < k < len(placed):
                m = len(placed) - k
                where += f" +{m} more position{'s' if m != 1 else ''}"
            if len(placed) < len(group):
                where = (
                    where + " " if where else ""
                ) + f"({len(group) - len(placed)} without a position)"
            return where

        def render(name: str, cap: int) -> Tuple[str, int, int]:
            """r22: (line, working machines, non-working machines), the line at most
            cap chars when shortening can make it so."""
            states = groups[name]
            order = sorted(states, key=lambda k: (k not in MACHINE_WORKING_STATES, k))
            shown = {s: sum(p is not None for p in states[s]) for s in order}
            kept = list(order)
            working = sum(len(states[s]) for s in order if s in MACHINE_WORKING_STATES)
            stalled = sum(len(states[s]) for s in order) - working

            def build() -> str:
                parts = []
                for state in kept:
                    group = states[state]
                    text = f"{len(group)} {state}"
                    if state not in MACHINE_WORKING_STATES:
                        text += f" at {where_text(group, shown[state])}"
                    parts.append(text)
                left = [s for s in order if s not in kept]
                if left:
                    n = sum(len(states[s]) for s in left)
                    parts.append(
                        f"{n} more machine{'s' if n != 1 else ''} in {len(left)} "
                        f"other state{'s' if len(left) != 1 else ''}"
                    )
                return f"- {name}: {working + stalled} ({', '.join(parts)})"

            line = build()
            while len(line) > cap:
                cut = [s for s in kept if s not in MACHINE_WORKING_STATES and shown[s] > 1]
                if cut:
                    s = max(cut, key=lambda k: (shown[k], k))
                    shown[s] -= max(1, shown[s] // 4)
                else:
                    stalled_kept = [s for s in kept if s not in MACHINE_WORKING_STATES]
                    if len(stalled_kept) <= 1:
                        break
                    kept.remove(min(stalled_kept, key=lambda k: (len(states[k]), k)))
                line = build()
            return line, working, stalled

        names = sorted(groups)
        # (line, working machines, non-working machines) per name
        entries: List[Tuple[str, int, int]] = [
            render(name, MACHINE_LINE_CHARS) for name in names
        ]

        lines = ["### Machine Status"]
        used = len(lines[0])
        # room kept for the last line when lines are left out
        budget = MACHINE_SECTION_CHARS - 80
        # r22: the lines that are listed share the room: a line shorter than its
        # share keeps its length, the longer ones are cut to the same cap
        listed, seen_working = [], 0
        for line, working, stalled in entries:
            if not stalled:
                seen_working += 1
                if seen_working > MACHINE_LINES_SHOWN:
                    continue
            listed.append(len(line) + 1)
        room, cap = budget - used, MACHINE_LINE_CHARS
        listed.sort()
        for i, n in enumerate(listed):
            share = room // (len(listed) - i)
            if n > share:
                cap = max(MACHINE_LINE_MIN_CHARS, min(cap, share - 1))
                break
            room -= n
        entries = [
            e if len(e[0]) <= cap else render(name, cap) for name, e in zip(names, entries)
        ]
        all_working_lines = more_working_lines = 0
        left_working = left_stalled = 0
        for line, working, stalled in entries:
            if not stalled:
                all_working_lines += 1
                if all_working_lines > MACHINE_LINES_SHOWN:
                    more_working_lines += 1
                    continue
            if used + 1 + len(line) > budget:
                left_working += working
                left_stalled += stalled
                continue
            lines.append(line)
            used += 1 + len(line)
        if more_working_lines:
            lines.append(f"- ({more_working_lines} more, all working)")
        if left_stalled and left_working:
            lines.append(
                f"- ({left_stalled} more non-working machines and "
                f"{left_working} more working machines not listed)"
            )
        elif left_stalled:
            lines.append(f"- ({left_stalled} more non-working machines not listed)")
        elif left_working:
            lines.append(f"- ({left_working} more working machines not listed)")
        return "\n".join(lines)

    @staticmethod
    def format_construction(status: Optional[Dict[str, Any]]) -> str:
        """Format the roboport networks, ghosts, deconstruction orders and blueprint
        placements (get_construction_status), or "" when there are none."""
        if not status:
            return ""

        def number(v) -> str:
            f = float(v)
            return str(int(f)) if f == int(f) else f"{f:g}"

        def waiting(groups) -> str:
            parts = [
                f"{g.get('count')} {g.get('reason')} (first at "
                f"({number(g.get('x', 0))}, {number(g.get('y', 0))}))"
                for g in groups or []
            ]
            return "; not being built: " + "; ".join(parts) if parts else ""

        lines = ["### Construction"]
        for n in status.get("networks") or []:
            stored = n.get("storage") or {}
            items = ", ".join(
                f"{k} {v}" for k, v in sorted(stored.items(), key=lambda kv: -kv[1])
            )
            more = (n.get("storage_item_types") or 0) - len(stored)
            if more > 0:
                items += f" (+{more} more item types)"
            lines.append(
                f"- roboport network {n.get('id')}: {n.get('roboports')} roboports "
                f"({n.get('roboports_no_power')} without power, {n.get('roboports_low_power')} low power), "
                f"construction robots {n.get('construction_robots')} ({n.get('construction_robots_idle')} idle), "
                f"logistic robots {n.get('logistic_robots')} ({n.get('logistic_robots_idle')} idle), "
                f"storage: {items or 'empty'}"
            )
        lines.append(
            f"- ghosts: {status.get('ghosts', 0)}"
            + waiting(status.get("ghosts_waiting"))
        )
        decon = waiting(status.get("deconstruction_waiting")).replace(
            "not being built", "not being removed"
        )
        lines.append(
            f"- marked for deconstruction: {status.get('deconstruction', 0)}{decon}"
        )
        for p in status.get("placements") or []:
            lines.append(
                f"- placement {p.get('id')} (blueprint {p.get('blueprint')} at "
                f"({number(p.get('x', 0))}, {number(p.get('y', 0))})): {p.get('ghosts_placed')} ghosts placed, "
                f"{p.get('built')} built, {p.get('ghosts_waiting')} still ghosts"
            )
        return "\n".join(lines)

    def format(
        self, observation: Observation, last_message_timestamp: float = 0.0
    ) -> FormattedObservation:
        """Format a complete observation into helpful strings"""
        # Convert Observation to dict if needed
        obs_dict = observation.to_dict()

        # Format each component based on include flags
        formatted_parts = []

        if self.include_inventory:
            inventory_str = self.format_inventory(obs_dict.get("inventory", []))
            formatted_parts.append(inventory_str)

        if self.include_entities:
            entities_str = self._entities_section(obs_dict.get("entities", []))
            formatted_parts.append(entities_str)

        if self.include_machine_status:
            machine_str = self.format_machine_status(obs_dict.get("entities", []))
            if machine_str:
                formatted_parts.append(machine_str)

        if self.include_flows:
            flows_str = self.format_flows(obs_dict.get("flows", {}))
            formatted_parts.append(flows_str)

        if self.include_functions:
            functions_str = self.format_functions(
                obs_dict.get("serialized_functions", [])
            )
            formatted_parts.append(functions_str)

        # Add research information
        if self.include_research:
            research_str = self.format_research(obs_dict.get("research", {}))
            formatted_parts.append(research_str)

        # Add game info
        if self.include_game_info:
            game_info_str = self.format_game_info(
                obs_dict.get("game_info", {}),
                score=obs_dict.get("score", 0.0),
                automated_score=obs_dict.get("automated_score", 0.0),
            )
            formatted_parts.append(game_info_str)

        # Add character positions
        if self.include_character_positions:
            character_positions_str = self.format_character_positions(
                obs_dict.get("character_positions", [])
            )
            formatted_parts.append(character_positions_str)

        # Add cliffs near the character
        if self.include_cliffs:
            cliffs_str = self.format_cliffs(obs_dict.get("cliffs"))
            if cliffs_str:
                formatted_parts.append(cliffs_str)

        # Add the electric network summaries
        if self.include_power:
            power_str = self.format_power(obs_dict.get("power_networks"))
            if power_str:
                formatted_parts.append(power_str)

        # Add the resource patches near the factory
        if self.include_resources:
            resources_str = self.format_resources(obs_dict.get("resources"))
            if resources_str:
                formatted_parts.append(resources_str)
        # Add roboport networks, ghosts and deconstruction orders (only once they exist)
        if self.include_construction:
            construction_str = self.format_construction(obs_dict.get("construction"))
            if construction_str:
                formatted_parts.append(construction_str)

        # Add optional components if they exist and are enabled
        if self.include_task:
            task_str = self.format_task(obs_dict.get("task_verification"))
            if task_str:
                formatted_parts.append(task_str)

            task_info_str = self.format_task_info(obs_dict.get("task_info"))
            if task_info_str:
                formatted_parts.append(task_info_str)

        if self.include_messages:
            messages_str = self.format_messages(
                obs_dict.get("messages", []), last_message_timestamp
            )
            if messages_str:
                formatted_parts.append(messages_str)

        # Add raw text output if enabled
        if self.include_raw_output:
            raw_text_str = self.format_raw_text(obs_dict.get("raw_text", ""))
            if raw_text_str:
                formatted_parts.append(raw_text_str)

        # Combine all parts with newlines
        raw_str = "\n\n".join(formatted_parts)

        # Create FormattedObservation with all fields, even if they're empty
        return FormattedObservation(
            inventory_str=self.format_inventory(obs_dict.get("inventory", []))
            if self.include_inventory
            else "",
            entities_str=self._entities_section(obs_dict.get("entities", []))
            if self.include_entities
            else "",
            flows_str=self.format_flows(obs_dict.get("flows", {}))
            if self.include_flows
            else "",
            task_str=self.format_task(obs_dict.get("task_verification"))
            if self.include_task
            else "",
            task_info_str=self.format_task_info(obs_dict.get("task_info"))
            if self.include_task
            else "",
            messages_str=self.format_messages(
                obs_dict.get("messages", []), last_message_timestamp
            )
            if self.include_messages
            else "",
            functions_str=self.format_functions(
                obs_dict.get("serialized_functions", [])
            )
            if self.include_functions
            else "",
            game_info_str=self.format_game_info(
                obs_dict.get("game_info", {}),
                score=obs_dict.get("score", 0.0),
                automated_score=obs_dict.get("automated_score", 0.0),
            )
            if self.include_game_info
            else "",
            raw_text_str=self.format_raw_text(obs_dict.get("raw_text", ""))
            if self.include_raw_output
            else "",
            character_positions_str=self.format_character_positions(
                obs_dict.get("character_positions", [])
            )
            if self.include_character_positions
            else "",
            cliffs_str=self.format_cliffs(obs_dict.get("cliffs"))
            if self.include_cliffs
            else "",
            power_str=self.format_power(obs_dict.get("power_networks"))
            if self.include_power
            else "",
            resources_str=self.format_resources(obs_dict.get("resources"))
            if self.include_resources
            else "",
            construction_str=self.format_construction(obs_dict.get("construction"))
            if self.include_construction
            else "",
            raw_str=raw_str,
        )


class TreeObservationFormatter(BasicObservationFormatter):
    """Formats observations using a prefix trie structure for token efficiency.

    Groups entities by type, then builds a trie based on shared key-value pairs.
    Shared attributes appear at branch nodes, unique attributes at leaves.
    Keys that vary vs are shared are computed dynamically from the actual data.

    Example output for 3 inserters with same direction but different positions:
        - inserter: 3
          [direction=SOUTH, status=WORKING, width=1, height=1]
            - position=(5.5, 3.5), drop_position=(5.5, 2.5)
            - position=(7.5, 3.5), drop_position=(7.5, 2.5)
            - position=(9.5, 3.5), drop_position=(9.5, 2.5)

    Args:
        excluded_keys: Optional set of keys to exclude from output entirely.
                      Defaults to empty set (include all keys).
    """

    def __init__(
        self,
        excluded_keys: Optional[set] = None,
        entity_budget_chars: Optional[int] = None,
        **kwargs,
    ):
        """Initialize the TreeObservationFormatter.

        Args:
            excluded_keys: Set of keys to exclude from output. Defaults to None (no exclusions).
            entity_budget_chars: If set, the entity section is kept within this many
                characters: the full listing when it fits, else the compact one
                (format_entities_compact). None: always the full listing.
            **kwargs: Additional arguments passed to BasicObservationFormatter.
        """
        super().__init__(**kwargs)
        self.excluded_keys = excluded_keys or set()
        self.entity_budget_chars = entity_budget_chars

    def _entities_section(self, entities: List[Any]) -> str:
        if self.entity_budget_chars is None:
            return self.format_entities(entities)
        return self.format_entities_within(entities, self.entity_budget_chars)

    @classmethod
    def format_entities_within(
        cls,
        entities: List[Any],
        budget_chars: int,
        excluded_keys: Optional[set] = None,
    ) -> str:
        """The full entity listing if it fits in budget_chars, else the compact one.
        Both give every list in full (belt contents and positions, pipe and pole
        positions, neighbours); only the compact one summarises, and says what."""
        full = cls.format_entities(entities, excluded_keys, uncapped=True)
        if len(full) <= budget_chars:
            return full
        return cls.format_entities_compact(entities, budget_chars, excluded_keys)

    @classmethod
    def format_entities_compact(
        cls,
        entities: List[Any],
        budget_chars: int,
        excluded_keys: Optional[set] = None,
    ) -> str:
        """Entity section within budget_chars, without dropping entities.

        Per type: values shared by all are listed once; entities with identical
        state are one line with all their positions (evenly spaced runs written
        as a..b by step, diagonal lines as (x0, y0)..(x1, y1) step (1, dy));
        geometry is relative to the entity (+(dx, dy)); 3+ differing groups are
        a table (keys once as columns). When that is still too long, detail is
        reduced one level at a time for all types alike (entity_compact levels:
        per-belt contents as counts, values that vary a lot as ranges (never
        status_detail),
        differing values other than connections / recipe / status left out,
        status and positions, counts and area), and the section names each
        type that was summarised and how. Entities are never left out."""
        from fle.env.gym_env.entity_compact import compact_section

        if not entities:
            return "### Entities\nNone found"
        return compact_section(
            cls._entity_groups(entities, excluded_keys, uncapped=True), budget_chars
        )

    @staticmethod
    def parse_entity_to_dict(entity_str: str) -> Dict[str, str]:
        """Parse an entity string into a dictionary of key-value pairs.

        Handles nested structures like Position(x=1.5, y=2.5), dicts, and lists correctly.
        """
        result = {}

        # Remove class wrapper if present: "ClassName(...)" -> content inside parens
        # Match patterns like "Inserter(...)" or "\n\tInserter(...)" or "AssemblingMachine1(...)"
        # Handle both escaped \\n\\t and actual whitespace
        class_match = re.match(
            r"^[\s\\nt]*([A-Za-z][A-Za-z0-9]*)\((.*)\)$", entity_str.strip(), re.DOTALL
        )
        if class_match:
            entity_str = class_match.group(2)

        # Parse key=value pairs, handling nested structures
        current_key = ""
        current_value = ""
        bracket_depth = 0  # []
        paren_depth = 0  # ()
        brace_depth = 0  # {}
        in_key = True
        in_quotes = False
        quote_char = None

        i = 0
        while i < len(entity_str):
            char = entity_str[i]

            # Track quotes - check for escaped quotes
            if char in "'\"" and (i == 0 or entity_str[i - 1] != "\\"):
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None

            # Track brackets, parens, and braces (only if not in quotes)
            if not in_quotes:
                if char == "[":
                    bracket_depth += 1
                elif char == "]":
                    bracket_depth -= 1
                elif char == "(":
                    paren_depth += 1
                elif char == ")":
                    paren_depth -= 1
                elif char == "{":
                    brace_depth += 1
                elif char == "}":
                    brace_depth -= 1

            # At top level (not inside any nested structure)
            at_top_level = (
                bracket_depth == 0
                and paren_depth == 0
                and brace_depth == 0
                and not in_quotes
            )

            # Key-value separator (only at top level)
            if char == "=" and in_key and at_top_level:
                in_key = False
                i += 1
                continue

            # Entry separator (comma at top level)
            if char == "," and at_top_level:
                if current_key.strip():
                    result[current_key.strip()] = current_value.strip()
                current_key = ""
                current_value = ""
                in_key = True
                i += 1
                # Skip whitespace after comma
                while i < len(entity_str) and entity_str[i] in " \t\n":
                    i += 1
                continue

            # Accumulate characters
            if in_key:
                current_key += char
            else:
                current_value += char

            i += 1

        # Don't forget the last pair
        if current_key.strip():
            result[current_key.strip()] = current_value.strip()

        return result

    @staticmethod
    def format_value(_key: str, value: str) -> str:
        """Format a value for display, cleaning up common patterns."""
        value = value.strip()

        # Clean Position values (only a single Position: a list of entities that
        # each contain a Position must not collapse to its first position)
        if value.startswith("Position(") and value.count("Position(") == 1:
            x_match = re.search(r"x=([\d.-]+)", value)
            y_match = re.search(r"y=([\d.-]+)", value)
            if x_match and y_match:
                x = float(x_match.group(1))
                y = float(y_match.group(1))
                return f"({x:.1f}, {y:.1f})"

        # Clean Direction enum
        if value.startswith("<Direction.") or value.startswith("Direction."):
            dir_match = re.search(r"Direction\.(\w+)", value)
            if dir_match:
                return dir_match.group(1)

        # Clean EntityStatus enum
        if value.startswith("<EntityStatus.") or value.startswith("EntityStatus."):
            status_match = re.search(r"EntityStatus\.(\w+)", value)
            if status_match:
                return status_match.group(1)

        # Clean Prototype
        if "Prototype" in value:
            proto_match = re.search(r"<Prototype\.([^:>]+)[:>]?", value)
            if proto_match:
                return f"Prototype.{proto_match.group(1)}"
            alt_match = re.search(r"Prototype\.([A-Za-z0-9_-]+)", value)
            if alt_match:
                return f"Prototype.{alt_match.group(1)}"

        # Clean Inventory repr
        if value.startswith("Inventory("):
            # Empty inventory
            if value == "Inventory()":
                return "[]"
            # Try to extract contents
            inner_match = re.match(r"Inventory\((.*)\)", value, re.DOTALL)
            if inner_match:
                return f"[{inner_match.group(1)}]"

        # Format inventory/item lists compactly: [{'name': 'coal', 'count': 18}] -> coal:18
        if (
            value.startswith("[")
            and "'name'" in value
            and ("'count'" in value or "'amount'" in value)
        ):
            try:
                # Try to parse as Python literal and format compactly
                import ast

                items = ast.literal_eval(value)
                if isinstance(items, list) and items:
                    formatted_items = []
                    for item in items:
                        if isinstance(item, dict):
                            name = item.get("name", item.get("type", "?"))
                            count = item.get(
                                "count", item.get("amount", item.get("value", 0))
                            )
                            formatted_items.append(f"{name}:{count}")
                    if formatted_items:
                        return "[" + ", ".join(formatted_items) + "]"
            except (ValueError, SyntaxError):
                pass  # Fall through to return original value

        # Format recipe dicts compactly: {'category': 'smelting', ...} -> extract key info
        if value.startswith("{") and "'category'" in value:
            try:
                import ast

                recipe = ast.literal_eval(value)
                if isinstance(recipe, dict):
                    # Extract key recipe info
                    parts = []
                    if recipe.get("category"):
                        parts.append(recipe["category"])
                    # Get inputs
                    ingredients = recipe.get("ingredients", [])
                    if ingredients:
                        ing_names = [
                            i.get("name", "?")
                            for i in ingredients
                            if isinstance(i, dict)
                        ]
                        if ing_names:
                            parts.append(f"in:{'+'.join(ing_names)}")
                    # Get outputs
                    products = recipe.get("products", [])
                    if products:
                        prod_names = [
                            p.get("name", "?") for p in products if isinstance(p, dict)
                        ]
                        if prod_names:
                            parts.append(f"out:{'+'.join(prod_names)}")
                    if parts:
                        return "{" + ", ".join(parts) + "}"
            except (ValueError, SyntaxError):
                pass  # Fall through to return original value

        # Try to format as number
        try:
            num = float(value)
            if num == int(num):
                return str(int(num))
            return f"{num:.1f}"
        except ValueError:
            pass

        # Remove quotes from simple strings
        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            return value[1:-1]

        return value

    @classmethod
    def build_entity_trie(
        cls, entities: List[Dict[str, str]], excluded_keys: Optional[set] = None
    ) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
        """Build a trie structure from a list of entity dictionaries.

        Dynamically determines which keys are shared (same value across all entities)
        vs which vary (different values per entity).

        Args:
            entities: List of parsed entity dictionaries
            excluded_keys: Optional set of keys to exclude from output

        Returns:
            Tuple of (shared_attributes, list_of_unique_attributes)
            - shared_attributes: dict of key-value pairs common to ALL entities
            - unique_attributes: list of dicts with per-entity unique attributes
        """
        excluded = excluded_keys or set()

        if not entities:
            return {}, []

        if len(entities) == 1:
            # Single entity - format all non-excluded keys as unique
            unique = {}
            for key, value in entities[0].items():
                if key not in excluded:
                    unique[key] = cls.format_value(key, value)
            return {}, [unique]

        # Find keys present in all entities
        all_keys = set(entities[0].keys())
        for entity in entities[1:]:
            all_keys &= set(entity.keys())

        # Remove excluded keys
        all_keys -= excluded

        # Dynamically determine shared vs varying keys by checking actual values
        shared = {}
        varying_keys = set()

        for key in all_keys:
            values = [e.get(key, "") for e in entities]
            unique_values = set(values)

            if len(unique_values) == 1 and values[0]:
                # All entities have the same non-empty value - this is a shared key
                shared[key] = cls.format_value(key, values[0])
            else:
                # Values differ across entities - this is a varying key
                varying_keys.add(key)

        # Build unique attributes for each entity (only varying keys + keys not in all entities)
        unique_list = []
        for entity in entities:
            unique = {}
            for key, value in entity.items():
                if key in excluded:
                    continue
                if key not in shared:
                    # This key either varies or isn't present in all entities
                    unique[key] = cls.format_value(key, value)
            unique_list.append(unique)

        return shared, unique_list

    @classmethod
    def build_nested_trie(
        cls,
        entities: List[Dict[str, str]],
        excluded_keys: Optional[set] = None,
        depth: int = 0,
        max_depth: int = 5,
    ) -> dict:
        """Build a nested trie structure that groups entities by shared varying values.

        Recursively groups entities: first extracts universally shared attributes,
        then groups remaining entities by the most common varying attribute value,
        and recurses on each subgroup.

        Args:
            entities: List of parsed entity dictionaries
            excluded_keys: Optional set of keys to exclude from output
            depth: Current recursion depth
            max_depth: Maximum recursion depth to prevent infinite loops

        Returns:
            Dict with structure:
            {
                'shared': {key: value, ...},  # Attributes shared by ALL entities at this level
                'children': [
                    {'shared': {...}, 'children': [...], 'leaves': [...]},  # Subgroups
                    ...
                ],
                'leaves': [{...}, {...}]  # Individual entity unique attributes (terminal)
            }
        """
        excluded = excluded_keys or set()

        if not entities:
            return {"shared": {}, "children": [], "leaves": []}

        if len(entities) == 1:
            # Single entity - all non-excluded keys become a leaf
            unique = {}
            for key, value in entities[0].items():
                if key not in excluded:
                    unique[key] = cls.format_value(key, value)
            return {"shared": {}, "children": [], "leaves": [unique]}

        # Find keys present in all entities
        all_keys = set(entities[0].keys())
        for entity in entities[1:]:
            all_keys &= set(entity.keys())
        all_keys -= excluded

        # Determine shared vs varying keys
        shared = {}
        varying_keys = []

        for key in all_keys:
            values = [e.get(key, "") for e in entities]
            unique_values = set(values)

            if len(unique_values) == 1 and values[0]:
                shared[key] = cls.format_value(key, values[0])
            else:
                # Track varying keys with their number of unique values
                varying_keys.append((key, len(unique_values), unique_values))

        # If no varying keys or max depth reached, return leaves
        if not varying_keys or depth >= max_depth:
            leaves = []
            for entity in entities:
                unique = {}
                for key, value in entity.items():
                    if key in excluded or key in shared:
                        continue
                    unique[key] = cls.format_value(key, value)
                leaves.append(unique)
            return {"shared": shared, "children": [], "leaves": leaves}

        # Sort varying keys by number of unique values (ascending) - fewer unique values = better for grouping
        varying_keys.sort(key=lambda x: x[1])

        # Try to find a good grouping key (one with few unique values but > 1)
        # Prefer keys that create meaningful subgroups (not too many, not just 1)
        best_group_key = None
        for key, num_unique, unique_vals in varying_keys:
            if 2 <= num_unique <= len(entities) // 2 + 1:
                best_group_key = key
                break

        # If no good grouping key found, just return leaves
        if best_group_key is None:
            leaves = []
            for entity in entities:
                unique = {}
                for key, value in entity.items():
                    if key in excluded or key in shared:
                        continue
                    unique[key] = cls.format_value(key, value)
                leaves.append(unique)
            return {"shared": shared, "children": [], "leaves": leaves}

        # Group entities by the best grouping key
        groups: Dict[str, List[Dict[str, str]]] = {}
        for entity in entities:
            group_value = entity.get(best_group_key, "")
            formatted_value = cls.format_value(best_group_key, group_value)
            if formatted_value not in groups:
                groups[formatted_value] = []
            groups[formatted_value].append(entity)

        # Build children by recursing on each group
        children = []
        # Pass parent's shared keys as exclusions to children
        child_excluded = excluded | set(shared.keys())
        for group_value, group_entities in sorted(groups.items()):
            # Remove the grouping key from entities before recursing
            sub_entities = []
            for entity in group_entities:
                sub_entity = {k: v for k, v in entity.items() if k != best_group_key}
                sub_entities.append(sub_entity)

            child_trie = cls.build_nested_trie(
                sub_entities,
                excluded_keys=child_excluded,
                depth=depth + 1,
                max_depth=max_depth,
            )
            # Add the grouping key-value to the child's shared attributes
            child_trie["shared"] = {best_group_key: group_value, **child_trie["shared"]}
            child_trie["count"] = len(group_entities)
            children.append(child_trie)

        return {"shared": shared, "children": children, "leaves": []}

    @classmethod
    def format_trie_output(
        cls,
        entity_type: str,
        count: int,
        shared: Dict[str, str],
        unique_list: List[Dict[str, str]],
        indent: str = "  ",
    ) -> str:
        """Format the flat trie structure as a string (non-nested version)."""
        # Header with count
        lines = [f"- {entity_type}: {count}"]

        # Shared attributes (if any)
        if shared:
            shared_str = ", ".join(f"{k}={v}" for k, v in sorted(shared.items()))
            lines.append(f"{indent}[{shared_str}]")

        # Unique attributes per entity
        for unique in unique_list:
            if unique:
                unique_str = ", ".join(f"{k}={v}" for k, v in sorted(unique.items()))
                lines.append(f"{indent}{indent}- {unique_str}")
            else:
                lines.append(f"{indent}{indent}- (no unique attributes)")

        return "\n".join(lines)

    @classmethod
    def format_nested_trie_output(
        cls,
        trie: dict,
        indent_level: int = 1,
        indent: str = "  ",
        parent_shared_keys: Optional[set] = None,
    ) -> List[str]:
        """Format a nested trie structure as lines of text.

        Args:
            trie: The trie dict with 'shared', 'children', 'leaves', and optionally 'count'
            indent_level: Current indentation level
            indent: Indentation string (default tab)
            parent_shared_keys: Keys already shown at parent level (to avoid redundancy)

        Returns:
            List of formatted lines
        """
        lines = []
        current_indent = indent * indent_level
        parent_keys = parent_shared_keys or set()

        # Get only the NEW shared attributes (not already shown at parent level)
        shared = trie.get("shared", {})
        new_shared = {k: v for k, v in shared.items() if k not in parent_keys}

        # Collect all keys shown so far (parent + this level)
        all_shown_keys = parent_keys | set(shared.keys())

        # Format shared attributes for this level (only new ones)
        if new_shared:
            shared_str = ", ".join(f"{k}={v}" for k, v in sorted(new_shared.items()))
            count_str = f": {trie['count']}" if "count" in trie else ""
            lines.append(f"{current_indent}[{shared_str}]{count_str}")

            # Children and leaves are nested under this branch
            child_indent_level = indent_level + 1
        else:
            # No new shared attributes at this level, don't add extra indentation
            child_indent_level = indent_level

        # Recursively format children
        for child in trie.get("children", []):
            child_lines = cls.format_nested_trie_output(
                child, child_indent_level, indent, parent_shared_keys=all_shown_keys
            )
            lines.extend(child_lines)

        # Format leaf nodes (individual entities) - exclude keys already shown
        leaf_indent = indent * child_indent_level
        for leaf in trie.get("leaves", []):
            if leaf:
                filtered_leaf = {
                    k: v for k, v in leaf.items() if k not in all_shown_keys
                }
                if filtered_leaf:
                    leaf_str = ", ".join(
                        f"{k}={v}" for k, v in sorted(filtered_leaf.items())
                    )
                    lines.append(f"{leaf_indent}- {leaf_str}")

        return lines

    # Default keys to exclude from entity output (internal/unimportant fields)
    DEFAULT_EXCLUDED_KEYS = {
        # "dimensions",
        "prototype",
        "type",
        # "health",
        "game",
        "id",
        # "tile_dimensions",
        "energy",
        "warnings",
        # "electrical_id",
    }

    # At most this many positions are listed for a pipe group or a power
    # network; the rest are counted as "(N more)"
    GROUP_POSITIONS_SHOWN = 6

    @staticmethod
    def _amount(v: Any) -> str:
        try:
            v = float(v)
        except (TypeError, ValueError):
            return "?"
        return f"{v:.0f}" if v >= 10 or v == int(v) else f"{v:.1f}"

    @classmethod
    def _compact_positions(cls, members: list, uncapped: bool = False) -> str:
        """First GROUP_POSITIONS_SHOWN member positions, then "(N more)".
        uncapped: every position, as evenly spaced runs (entity_compact.positions_text)."""
        if uncapped:
            from fle.env.gym_env.entity_compact import positions_text

            points = []
            for m in members:
                pos = getattr(m, "position", None)
                if pos is None and isinstance(m, dict):
                    pos = m.get("position")
                if isinstance(pos, dict):
                    x, y = pos.get("x"), pos.get("y")
                else:
                    x = getattr(pos, "x", None) if pos is not None else None
                    y = getattr(pos, "y", None) if pos is not None else None
                if x is not None and y is not None:
                    points.append((float(x), float(y)))
            return "[" + positions_text(points) + "]"
        shown = []
        for m in members[: cls.GROUP_POSITIONS_SHOWN]:
            pos = getattr(m, "position", None)
            if pos is None and isinstance(m, dict):
                pos = m.get("position")
            x = getattr(pos, "x", None) if pos is not None else None
            y = getattr(pos, "y", None) if pos is not None else None
            if isinstance(pos, dict):
                x, y = pos.get("x"), pos.get("y")
            if x is None or y is None:
                continue
            shown.append(f"({float(x):.1f}, {float(y):.1f})")
        more = len(members) - min(len(members), cls.GROUP_POSITIONS_SHOWN)
        if more > 0:
            shown.append(f"({more} more)")
        return "[" + ", ".join(shown) + "]"

    @classmethod
    def _compact_fluid_power(
        cls, key: str, value: Any, uncapped: bool = False
    ) -> Optional[str]:
        """Compact text for fluidboxes, pipe groups and power networks, or None to
        format normally. Powers read like "900 kW", energies like "5 MJ".

        fluid_box (one entry per fluidbox holding fluid):
            [water 200/200 input, steam 200/200 165C output]
        pipes / poles (a pipe group's pipes, a power network's poles): their
            positions, at most GROUP_POSITIONS_SHOWN, then "(N more)".
        """
        if key == "fluid_box" and isinstance(value, list):
            boxes = []
            for box in value:
                if not isinstance(box, dict) or not box.get("name"):
                    continue
                text = f"{str(box['name']).strip(chr(34))} {cls._amount(box.get('amount'))}"
                if box.get("capacity"):
                    text += f"/{cls._amount(box['capacity'])}"
                temperature = box.get("temperature")
                if isinstance(temperature, (int, float)) and temperature != 15:
                    text += f" {temperature:.0f}C"
                if box.get("type"):
                    text += f" {str(box['type']).strip(chr(34))}"
                boxes.append(text)
            return "[" + ", ".join(boxes) + "]"
        if key in ("pipes", "poles") and isinstance(value, list):
            return cls._compact_positions(value, uncapped)
        if key in POWER_KEYS and isinstance(value, (int, float)):
            return format_watts(value)
        if key in ENERGY_KEYS and isinstance(value, (int, float)):
            return format_joules(value)
        if key == "satisfaction" and isinstance(value, (int, float)):
            return f"{value:.0%}"
        if key == "network" and isinstance(value, dict):
            return format_network(value)
        return None

    @classmethod
    def format_value_from_object(
        cls, key: str, value: Any, uncapped: bool = False
    ) -> str:
        """Format a Python object value for display.

        Args:
            key: The attribute name
            value: The Python object value

        Returns:
            Formatted string representation
        """
        from fle.env.entities import Position, Direction, EntityStatus, Inventory

        # Handle None
        if value is None:
            return "None"

        # Fluid and power fields in compact, factual form
        compact = cls._compact_fluid_power(key, value, uncapped)
        if compact is not None:
            return compact

        # Handle Position objects
        if isinstance(value, Position):
            return f"({value.x:.1f}, {value.y:.1f})"

        # Handle Direction enum
        if isinstance(value, Direction):
            return value.name

        # Handle EntityStatus enum
        if isinstance(value, EntityStatus):
            return value.name

        # Handle Inventory objects
        if isinstance(value, Inventory):
            items = dict(value)
            if not items:
                return "[]"
            item_strs = [f"{k}:{v}" for k, v in items.items() if v > 0]
            return "[" + ", ".join(item_strs) + "]" if item_strs else "[]"

        # Handle other enums
        if hasattr(value, "name") and hasattr(value, "value"):
            return value.name

        # Handle lists
        if isinstance(value, list):
            if not value:
                return "[]"
            # Format list items
            formatted_items = [
                cls.format_value_from_object(key, item, uncapped) for item in value
            ]
            return "[" + ", ".join(formatted_items) + "]"

        # Handle dicts (like recipes)
        if isinstance(value, dict):
            if not value:
                return "{}"
            # Check if it's a recipe-like dict
            if "category" in value:
                parts = []
                if value.get("category"):
                    parts.append(str(value["category"]))
                ingredients = value.get("ingredients", [])
                if ingredients:
                    ing_names = [
                        i.get("name", "?") for i in ingredients if isinstance(i, dict)
                    ]
                    if ing_names:
                        parts.append(f"in:{'+'.join(ing_names)}")
                products = value.get("products", [])
                if products:
                    prod_names = [
                        p.get("name", "?") for p in products if isinstance(p, dict)
                    ]
                    if prod_names:
                        parts.append(f"out:{'+'.join(prod_names)}")
                if parts:
                    return "{" + ", ".join(parts) + "}"
            # Generic dict formatting
            return str(value)

        # Handle floats
        if isinstance(value, float):
            if value == int(value):
                return str(int(value))
            return f"{value:.1f}"

        # Handle ints
        if isinstance(value, int):
            return str(value)

        # Handle strings - remove quotes
        if isinstance(value, str):
            return value

        # Fallback to string representation
        return str(value)

    @classmethod
    def entity_dict_to_formatted(
        cls,
        entity_dict: Dict[str, Any],
        excluded_keys: Optional[set] = None,
        uncapped: bool = False,
    ) -> Dict[str, str]:
        """Convert an entity dict (from Pydantic __dict__) to a formatted dict.

        Args:
            entity_dict: Raw entity dictionary from Pydantic __dict__
            excluded_keys: Keys to exclude from output

        Returns:
            Dict with string keys and formatted string values
        """
        excluded = excluded_keys or cls.DEFAULT_EXCLUDED_KEYS
        result = {}

        for key, value in entity_dict.items():
            # Remove leading underscore from Pydantic internal fields
            clean_key = key.lstrip("_")

            # Skip excluded keys
            if clean_key in excluded:
                continue

            # Skip private attributes
            if clean_key.startswith("__"):
                continue

            # Only entities whose status has a reason carry a status detail
            if clean_key == "status_detail" and not value:
                continue

            # Format the value
            result[clean_key] = cls.format_value_from_object(clean_key, value, uncapped)

        return result

    # Caps for the compact belt summaries (each overflow shows "(N more)")
    BELT_ENDS_CAP = 3
    BELT_CONTENTS_CAP = 6

    @staticmethod
    def _attr(obj: Any, key: str, default: Any = None) -> Any:
        """Read a field from an entity object or from its dict form."""
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
            return obj.get("_" + key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _pos_str(pos: Any) -> str:
        if pos is None:
            return "?"
        if isinstance(pos, dict):
            x, y = pos.get("x"), pos.get("y")
        else:
            x, y = getattr(pos, "x", None), getattr(pos, "y", None)
        if x is None or y is None:
            return "?"
        return f"({float(x):.1f}, {float(y):.1f})"

    @staticmethod
    def _items_str(items: Any) -> str:
        """{'iron-plate': 3, 'coal': 0} -> 'iron-plate:3' (zero counts dropped)."""
        try:
            pairs = [(k, v) for k, v in dict(items or {}).items() if v]
        except (TypeError, ValueError):
            return str(items)
        return ", ".join(
            f"{k}:{v:g}" if isinstance(v, float) else f"{k}:{v}" for k, v in pairs
        )

    @classmethod
    def _capped(cls, parts: List[str], cap: Optional[int], sep: str = ", ") -> str:
        """parts joined, the first `cap` of them then "(N more)"; cap None: all."""
        if cap is None:
            return sep.join(parts)
        shown = sep.join(parts[:cap])
        if len(parts) > cap:
            shown += f"{sep}({len(parts) - cap} more)"
        return shown

    @classmethod
    def _compact_special(
        cls,
        entity_name: str,
        entity: Dict[str, Any],
        formatted: Dict[str, str],
        uncapped: bool = False,
    ) -> Dict[str, str]:
        """Entity-specific compact views (belt groups, inserters). Facts only."""
        try:
            neighbours = entity.get("neighbours")
            if (
                isinstance(neighbours, list)
                and neighbours
                and "neighbours" in formatted
            ):
                formatted = dict(formatted)
                formatted["neighbours"] = cls._compact_neighbours(neighbours, uncapped)
            if entity_name == "belt-group" or (
                "belts" in entity and isinstance(entity.get("belts"), list)
            ):
                return cls._compact_belt_group(entity, formatted, uncapped)
            if str(entity_name).endswith("inserter") and "drop_position" in formatted:
                return cls._compact_inserter(entity, formatted)
        except Exception:
            return formatted
        return formatted

    NEIGHBOURS_CAP = 4

    @classmethod
    def _compact_neighbours(cls, neighbours: List[Any], uncapped: bool = False) -> str:
        """[name (x, y), ...] instead of each neighbour's full repr."""
        parts = []
        for n in neighbours:
            name = cls._attr(n, "name", "?")
            parts.append(f"{name} {cls._pos_str(cls._attr(n, 'position'))}")
        return "[" + cls._capped(parts, None if uncapped else cls.NEIGHBOURS_CAP) + "]"

    @classmethod
    def _compact_inserter(
        cls, entity: Dict[str, Any], formatted: Dict[str, str]
    ) -> Dict[str, str]:
        """Inserter: what is at its pickup and drop positions, and what it holds."""
        out = dict(formatted)
        for key in ("pickup_target", "drop_target"):
            out[key] = cls._attr(entity, key) or "none"
        held = cls._attr(entity, "held_item")
        out.pop("held_item", None)
        name = cls._attr(held, "name") if held else None
        out["held"] = f"{name}:{cls._attr(held, 'count', 1)}" if name else "empty"
        return out

    @classmethod
    def _compact_belt_group(
        cls, entity: Dict[str, Any], formatted: Dict[str, str], uncapped: bool = False
    ) -> Dict[str, str]:
        """A belt group as counts: belts by type, ends, per-lane totals (L/R), and
        the belts that hold items, capped with "(N more)". uncapped: every end and
        every belt holding items, plus belt_positions: where each belt is, by
        direction, as evenly spaced runs.

        L/R are the belt's own left/right lanes looking along its direction
        (Factorio transport lines 1 and 2)."""
        belts = list(entity.get("belts") or [])
        out = {k: v for k, v in formatted.items() if k not in ("belts",)}

        by_type: Dict[str, int] = {}
        lane_totals = {"left": {}, "right": {}}
        holding = []
        full = 0
        by_direction: Dict[str, List[Tuple[float, float]]] = {}
        for b in belts:
            if uncapped:
                pos = cls._attr(b, "position")
                x = cls._attr(pos, "x") if pos is not None else None
                y = cls._attr(pos, "y") if pos is not None else None
                if x is not None and y is not None:
                    d = cls._attr(b, "direction")
                    d = getattr(d, "name", None) or str(d or "?")
                    by_direction.setdefault(d, []).append((float(x), float(y)))
            name = cls._attr(b, "name", "?")
            by_type[name] = by_type.get(name, 0) + 1
            inv = cls._attr(b, "inventory", {}) or {}
            lanes = {}
            if isinstance(inv, dict) and ("left" in inv or "right" in inv):
                for lane in ("left", "right"):
                    try:
                        lanes[lane] = {
                            k: v for k, v in dict(inv.get(lane) or {}).items() if v
                        }
                    except (TypeError, ValueError):
                        lanes[lane] = {}
                    for k, v in lanes[lane].items():
                        lane_totals[lane][k] = lane_totals[lane].get(k, 0) + v
            warnings = cls._attr(b, "warnings", []) or []
            if any("full" in str(w) for w in warnings):
                full += 1
            if any(lanes.values()):
                bits = []
                if lanes.get("left"):
                    bits.append("L[" + cls._items_str(lanes["left"]) + "]")
                if lanes.get("right"):
                    bits.append("R[" + cls._items_str(lanes["right"]) + "]")
                holding.append(
                    f"{cls._pos_str(cls._attr(b, 'position'))} " + " ".join(bits)
                )

        out["belts"] = ", ".join(f"{n}:{c}" for n, c in sorted(by_type.items())) or "0"
        for key in ("inputs", "outputs"):
            ends = entity.get(key)
            if isinstance(ends, list):
                out[key] = (
                    "["
                    + cls._capped(
                        [cls._pos_str(cls._attr(e, "position")) for e in ends],
                        None if uncapped else cls.BELT_ENDS_CAP,
                    )
                    + "]"
                )
        out["lanes"] = (
            f"L[{cls._items_str(lane_totals['left'])}] "
            f"R[{cls._items_str(lane_totals['right'])}]"
        )
        if full:
            out["full_belts"] = str(full)
        if holding:
            out["holding"] = f"{len(holding)} belts: " + cls._capped(
                holding, None if uncapped else cls.BELT_CONTENTS_CAP, sep="; "
            )
        if by_direction:
            from fle.env.gym_env.entity_compact import positions_text

            out["belt_positions"] = "; ".join(
                f"{d} {positions_text(pts)}" for d, pts in sorted(by_direction.items())
            )
        return out

    @classmethod
    def _entity_groups(
        cls,
        entities: List[Any],
        excluded_keys: Optional[set] = None,
        uncapped: bool = False,
    ) -> Dict[str, List[Dict[str, str]]]:
        """Entities as {type: [formatted key/value dicts]}. uncapped: lists inside
        values (belt contents and ends, pipe / pole positions, neighbours) are
        given in full instead of their first few then "(N more)"."""
        excluded = (
            excluded_keys if excluded_keys is not None else cls.DEFAULT_EXCLUDED_KEYS
        )

        # Group entities by type (name field)
        entity_groups: Dict[str, List[Dict[str, str]]] = {}

        for entity in entities:
            # Handle both dict and string formats for backwards compatibility
            if isinstance(entity, dict):
                # Get entity name for grouping
                entity_name = entity.get("name") or entity.get("_name") or "unknown"
                if hasattr(entity_name, "lstrip"):
                    entity_name = entity_name.lstrip("_")

                # Convert to formatted dict
                formatted = cls.entity_dict_to_formatted(entity, excluded, uncapped)
                formatted = cls._compact_special(
                    entity_name, entity, formatted, uncapped
                )

                if entity_name not in entity_groups:
                    entity_groups[entity_name] = []
                entity_groups[entity_name].append(formatted)
            elif isinstance(entity, str):
                # Legacy string format - parse it
                name_pattern = re.compile(r"\bname\s*=\s*'?\"?([A-Za-z0-9_-]+)'?\"?")
                n = name_pattern.search(entity)
                entity_name = n.group(1) if n else "unknown"

                parsed = cls.parse_entity_to_dict(entity)
                # Format the parsed values
                formatted = {}
                for k, v in parsed.items():
                    if k not in excluded:
                        formatted[k] = cls.format_value(k, v)

                if entity_name not in entity_groups:
                    entity_groups[entity_name] = []
                entity_groups[entity_name].append(formatted)

        return entity_groups

    @classmethod
    def format_entities(
        cls,
        entities: List[Any],
        excluded_keys: Optional[set] = None,
        uncapped: bool = False,
    ) -> str:
        """Format entity information using nested trie-based compression.

        Args:
            entities: List of entity dicts (from Pydantic __dict__) or strings
            excluded_keys: Optional set of keys to exclude from output

        Returns:
            Formatted string with entities grouped by type and compressed using nested trie structure
        """
        if not entities:
            return "### Entities\nNone found"

        entity_groups = cls._entity_groups(entities, excluded_keys, uncapped)

        # Format each entity group using nested trie structure
        group_strs = []
        for entity_type, group in sorted(entity_groups.items()):
            count = len(group)

            # Build nested trie structure (group is already list of formatted dicts)
            trie = cls.build_nested_trie(
                group, excluded_keys=set()
            )  # Already excluded above

            # Format the header
            lines = [f"- {entity_type}: {count}"]

            # Collect top-level shared keys
            top_shared = trie.get("shared", {})
            top_shared_keys = set(top_shared.keys())

            # Determine starting indent level for children
            if top_shared:
                # Format top-level shared attributes
                shared_str = ", ".join(
                    f"{k}={v}" for k, v in sorted(top_shared.items())
                )
                lines.append(f"  [{shared_str}]")
                # Children start at indent level 2 (nested under the shared attributes)
                child_start_level = 2
            else:
                # No top-level shared, children start at indent level 1
                child_start_level = 1

            # Format children (nested groups) - pass top-level shared keys to avoid redundancy
            for child in trie.get("children", []):
                child_lines = cls.format_nested_trie_output(
                    child,
                    indent_level=child_start_level,
                    indent="  ",
                    parent_shared_keys=top_shared_keys,
                )
                lines.extend(child_lines)

            # Format leaves (individual entities at top level) - exclude top-level shared keys
            leaf_indent = "  " * child_start_level
            for leaf in trie.get("leaves", []):
                if leaf:
                    filtered_leaf = {
                        k: v for k, v in leaf.items() if k not in top_shared_keys
                    }
                    if filtered_leaf:
                        leaf_str = ", ".join(
                            f"{k}={v}" for k, v in sorted(filtered_leaf.items())
                        )
                        lines.append(f"{leaf_indent}- {leaf_str}")

            group_strs.append("\n".join(lines))

        return "### Entities\n" + "\n".join(group_strs)
