"""The factory-image pipe renderer joins a pipe to a neighbouring pipe-to-ground only
when the pipe-to-ground's above-ground opening faces it. Entity directions are Factorio
2.0's 16-way values (0 N, 4 E, 8 S, 12 W), as the other renderers use them."""

import pytest

from fle.env.tools.admin.render.renderers import pipe

# (dx, dy) of the neighbour -> index in get_around's [N, E, S, W]
SIDES = {(0, -1): 0, (1, 0): 1, (0, 1): 2, (-1, 0): 3}
# the direction the neighbour's opening must face to reach the pipe at the centre
FACING_US = {(0, -1): 8, (1, 0): 12, (0, 1): 0, (-1, 0): 4}


class Grid:
    center_x, center_y = 0.5, 0.5

    def __init__(self, neighbours):
        self.n = neighbours

    def get_relative(self, dx, dy):
        return self.n.get((dx, dy))


@pytest.mark.parametrize("offset", list(SIDES))
@pytest.mark.parametrize("direction", [0, 4, 8, 12])
def test_pipe_joins_a_pipe_to_ground_only_when_it_faces_the_pipe(offset, direction):
    ptg = {"name": "pipe-to-ground", "direction": direction,
           "position": {"x": 0.5 + offset[0], "y": 0.5 + offset[1]}}
    around = pipe.get_around({"name": "pipe"}, Grid({offset: ptg}))
    expected = [False] * 4
    expected[SIDES[offset]] = direction == FACING_US[offset]
    assert [bool(v) for v in around] == expected


def test_constants_are_sixteen_way():
    assert (pipe.NORTH, pipe.EAST, pipe.SOUTH, pipe.WEST) == (0, 4, 8, 12)
