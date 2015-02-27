import mock
import pytest

from ..machine_controller import MachineController
from ..sdram_file import SDRAMFile


@pytest.fixture
def mock_controller():
    cn = mock.Mock(spec=MachineController)
    return cn


class TestSDRAMFile(object):
    """Test the SDRAM file-like object."""
    @pytest.mark.parametrize("x, y", [(1, 3), (3, 0)])
    @pytest.mark.parametrize("start_address", [0x60000000, 0x61000000])
    @pytest.mark.parametrize("lengths", [[100, 200], [100], [300, 128, 32]])
    def test_read(self, mock_controller, x, y, start_address, lengths):
        sdram_file = SDRAMFile(mock_controller, x, y,
                               start_address=start_address)
        assert sdram_file.tell() == 0

        # Perform the reads, check that the address is progressed
        calls = []
        offset = 0
        for n_bytes in lengths:
            sdram_file.read(n_bytes)
            assert sdram_file.tell() == offset + n_bytes
            assert sdram_file.address == start_address + offset + n_bytes
            calls.append(mock.call(x, y, 0, start_address + offset, n_bytes))
            offset = offset + n_bytes

        # Check the reads caused the appropriate calls to the machine
        # controller.
        mock_controller.read.assert_has_calls(calls)

    def test_read_beyond(self, mock_controller):
        sdram_file = SDRAMFile(mock_controller, 0, 0,
                               start_address=0, end_address=10)
        sdram_file.read(100)
        mock_controller.read.assert_called_with(0, 0, 0, 0, 10)

        assert sdram_file.read(1) == b''
        assert mock_controller.read.call_count == 1

    @pytest.mark.parametrize("x, y", [(4, 2), (255, 1)])
    @pytest.mark.parametrize("start_address", [0x60000004, 0x61000003])
    @pytest.mark.parametrize("lengths", [[100, 200], [100], [300, 128, 32]])
    def test_write(self, mock_controller, x, y, start_address, lengths):
        sdram_file = SDRAMFile(mock_controller, x, y,
                               start_address=start_address)
        assert sdram_file.tell() == 0

        # Perform the reads, check that the address is progressed
        calls = []
        offset = 0
        for i, n_bytes in enumerate(lengths):
            n_written = sdram_file.write(chr(i % 256) * n_bytes)
            assert n_written == n_bytes
            assert sdram_file.tell() == offset + n_bytes
            assert sdram_file.address == start_address + offset + n_bytes
            calls.append(mock.call(x, y, 0, start_address + offset,
                                   chr(i % 256) * n_bytes))
            offset = offset + n_bytes

        # Check the reads caused the appropriate calls to the machine
        # controller.
        mock_controller.write.assert_has_calls(calls)

    def test_write_beyond(self, mock_controller):
        sdram_file = SDRAMFile(mock_controller, 0, 0,
                               start_address=0, end_address=10)

        assert sdram_file.write(b"\x00\x00" * 12) == 10

        assert sdram_file.write(b"\x00") == 0
        assert mock_controller.write.call_count == 1

    @pytest.mark.parametrize("start_address", [0x60000004, 0x61000003])
    @pytest.mark.parametrize("seeks", [(100, -3, 32, 5, -7)])
    def test_seek(self, mock_controller, seeks, start_address):
        sdram_file = SDRAMFile(mock_controller, 0, 0,
                               start_address=start_address)
        assert sdram_file.tell() == 0

        cseek = 0
        for seek in seeks:
            sdram_file.seek(seek)
            assert sdram_file.tell() == cseek + seek
            cseek += seek
