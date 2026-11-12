"""break and continue in programs run by FactorioNamespace act as in Python. Server-free.

The namespace runs top-level statements itself (execute_node). A break or continue
nested in an if or try used to set the loop state without stopping the rest of the
loop body, and an inner loop after it reset the state, so an outer break was lost.
"""

import ast

import pytest

from fle.env.namespace import FactorioNamespace, LoopContext


@pytest.fixture
def run():
    ns = FactorioNamespace.__new__(FactorioNamespace)
    ns.line_value = 0
    ns.persistent_vars = {}
    ns.player_location = None
    ns._protected_names = set()
    ns.capture_whole_output = False

    def run(source: str) -> list:
        ns.loop_context = LoopContext()
        out: list = []
        eval_dict = {"out": out, "range": range, "ValueError": ValueError}
        for node in ast.parse(source).body:
            ns.execute_node(node, eval_dict)
        return out

    return run


def python(source: str) -> list:
    out: list = []
    exec(source, {"out": out})
    return out


CASES = {
    "continue in if": """
for i in range(4):
    if i == 1:
        continue
    out.append(i)
""",
    "break in if": """
for i in range(5):
    if i == 2:
        break
    out.append(i)
""",
    "continue in else branch": """
for i in range(4):
    if i % 2:
        out.append(i)
    else:
        continue
    out.append(-i)
""",
    "outer break before an inner loop": """
done = False
for a in range(3):
    if done:
        break
    for b in range(2):
        out.append((a, b))
    done = True
    out.append(a)
""",
    "break in if, inner loop after it": """
for a in range(3):
    out.append(a)
    if a == 1:
        break
    for b in range(2):
        out.append((a, b))
""",
    "inner break leaves the outer loop running": """
for a in range(3):
    for b in range(3):
        if b == 1:
            break
        out.append((a, b))
    out.append(a)
""",
    "while with continue and break": """
i = 0
while i < 10:
    i += 1
    if i % 2:
        continue
    if i > 6:
        break
    out.append(i)
""",
    "break in try body skips else": """
for i in range(3):
    try:
        if i == 1:
            break
        out.append(i)
    except ValueError:
        out.append("except")
    else:
        out.append("else")
""",
    "continue in try body runs finally in full": """
for i in range(3):
    try:
        if i == 1:
            continue
        out.append(i)
    finally:
        out.append("f")
        out.append("g")
    out.append("after")
""",
    "break in except handler": """
for i in range(3):
    try:
        raise ValueError(i)
    except ValueError:
        out.append(i)
        if i == 1:
            break
    out.append("after")
""",
    "for-else after break and without": """
for i in range(3):
    if i == 1:
        break
else:
    out.append("no break")
for i in range(2):
    if i == 5:
        break
else:
    out.append("else ran")
""",
}


@pytest.mark.parametrize("name", list(CASES))
def test_matches_python(run, name):
    assert run(CASES[name]) == python(CASES[name])


def test_examples(run):
    assert run(CASES["continue in if"]) == [0, 2, 3]
    assert run(CASES["outer break before an inner loop"]) == [(0, 0), (0, 1), 0]
