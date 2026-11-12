"""The tool signatures the agents read (SchemaGenerator: str(inspect.signature(cls.__call__)))
must be the same text in every process: a default whose repr holds a memory address (a bare
object() sentinel) changed the prompt on every restart and showed the model an address."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RENDER = r"""
import sys, warnings
warnings.filterwarnings("ignore")
from fle.env.utils.controller_loader.schema_generator import SchemaGenerator
print(SchemaGenerator(sys.argv[1]).generate_schema(with_docstring=False))
"""


def _render():
    out = subprocess.run(
        [sys.executable, "-c", RENDER, str(ROOT / "fle/env/tools/agent")],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return out.stdout


def test_tool_signatures_are_the_same_in_two_processes_and_hold_no_address():
    a, b = _render(), _render()
    assert a == b
    assert "inspect_inventory(" in a
    assert not re.search(r" at 0x[0-9a-f]+", a), re.findall(r".*at 0x[0-9a-f]+.*", a)


def test_inspect_inventory_default_reads_as_your_own_inventory():
    a = _render()
    line = next(ln for ln in a.splitlines() if ln.startswith("inspect_inventory("))
    assert "entity=<your own inventory>" in line, line
