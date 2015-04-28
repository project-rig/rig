import mock
import pytest

from rig.machine_control import MachineController
from rig.machine_control.machine_controller import MemoryIO
from rig.machine_control.utils import sdram_alloc_for_vertices
from rig.machine import Cores, SDRAM


@pytest.mark.parametrize("core_as_tag", [True, False])
def test_sdram_alloc_for_vertices(core_as_tag):
    """Test allocing and getting a map of vertices to file-like objects
    when multiple blocks of memory are requested.
    """
    # Create 3 vertices and make them require some amounts of SDRAM
    vertices = [mock.Mock(name="vertex") for _ in range(4)]
    placements = {vertices[0]: (0, 0),
                  vertices[1]: (0, 0),
                  vertices[2]: (1, 1),
                  vertices[3]: (1, 1),
                  }
    allocations = {vertices[0]: {Cores: slice(1, 2), SDRAM: slice(0, 400)},
                   vertices[1]: {Cores: slice(2, 3), SDRAM: slice(400, 600)},
                   vertices[2]: {Cores: slice(1, 2), SDRAM: slice(124, 224)},
                   vertices[3]: {Cores: slice(2, 3)},
                   }

    # Create the controller
    cn = MachineController("localhost")

    def sdram_alloc(size, tag, x, y, app_id):
        return {
            (0, 0, 1): 0x67800000,
            (0, 0, 2): 0x60000000,
            (1, 1, 1): 0x67800000,
        }[(x, y, tag)]

    if core_as_tag:
        cn.sdram_alloc = mock.Mock(wraps=sdram_alloc)
    else:
        cn.sdram_alloc = mock.Mock(return_value=0x60080000)

    # Perform the SDRAM allocation
    with cn(app_id=33):
        allocs = sdram_alloc_for_vertices(cn, placements, allocations,
                                          core_as_tag=core_as_tag)

    # Ensure the correct calls were made to sdram_alloc
    cn.sdram_alloc.assert_has_calls([
        mock.call(400, 1 if core_as_tag else 0, 0, 0, 33),
        mock.call(200, 2 if core_as_tag else 0, 0, 0, 33),
        mock.call(100, 1 if core_as_tag else 0, 1, 1, 33),
    ], any_order=True)

    # Ensure that every vertex has a memory file-like
    assert len(allocs) == 3
    assert isinstance(allocs[vertices[0]], MemoryIO)
    assert allocs[vertices[0]]._x == 0
    assert allocs[vertices[0]]._y == 0
    assert allocs[vertices[0]]._machine_controller is cn
    if core_as_tag:
        assert allocs[vertices[0]]._start_address == 0x67800000
        assert allocs[vertices[0]]._end_address == 0x67800000 + 400

    assert isinstance(allocs[vertices[1]], MemoryIO)
    assert allocs[vertices[1]]._x == 0
    assert allocs[vertices[1]]._y == 0
    assert allocs[vertices[1]]._machine_controller is cn
    if core_as_tag:
        assert allocs[vertices[1]]._start_address == 0x60000000
        assert allocs[vertices[1]]._end_address == 0x60000000 + 200

    assert isinstance(allocs[vertices[2]], MemoryIO)
    assert allocs[vertices[2]]._x == 1
    assert allocs[vertices[2]]._y == 1
    assert allocs[vertices[2]]._machine_controller is cn
    if core_as_tag:
        assert allocs[vertices[2]]._start_address == 0x67800000
        assert allocs[vertices[2]]._end_address == 0x67800000 + 100
