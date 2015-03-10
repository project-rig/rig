import pytest

from mock import Mock

from rig.machine_control import BMPController
from rig.machine_control.bmp_controller import BMPInfo
from rig.machine_control.packets import SCPPacket

@pytest.fixture(scope="module")
def live_controller(bmp_ip):
    return BMPController(bmp_ip)


@pytest.fixture(scope="module")
def sver_response():
    return BMPInfo(code_block=1, frame_id=2, can_id=3, board_id=4,
                   version=123/100., buffer_size=512, build_date=1234,
                   version_string="Hello, World!")

@pytest.fixture(scope="module")
def bc_mock_sver(sver_response):
    # A BMPController with a pre-programmed fake sver response to all SCP
    # commands.
    arg1 = (
        (sver_response.code_block << 24) |
        (sver_response.frame_id << 16) |
        (sver_response.can_id << 8) |
        sver_response.board_id
    )
    
    version = int(sver_response.version * 100)
    arg2 = (version << 16) | sver_response.buffer_size
    
    arg3 = sver_response.build_date
    
    bc = BMPController("127.0.0.1")
    bc._send_scp = Mock()
    bc._send_scp.return_value = Mock(spec_set=SCPPacket)
    bc._send_scp.return_value.arg1 = arg1
    bc._send_scp.return_value.arg2 = arg2
    bc._send_scp.return_value.arg3 = arg3
    bc._send_scp.return_value.data = \
        sver_response.version_string.encode("utf-8")
    
    return bc

@pytest.mark.incremental
class TestBMPControllerLive(object):
    """Test the BMP controller against real hardware."""
    
    def test_scp_data_length(self, live_controller):
        assert live_controller.scp_data_length >= 256
    
    def test_get_software_version(self, live_controller):
        # Check "SVER" works
        sver = live_controller.get_software_version(0, 0, 0)
        assert sver.version >= 1.3
        assert "BMP" in sver.version_string


class TestBMPController(object):
    """Offline tests of the BMPController."""
    
    def test_single_hostname(self):
        bc = BMPController("127.0.0.1")
        assert set(bc.connections) == set([(0, 0)])
        assert bc.connections[(0, 0)].sock.getsockname()[0] == "127.0.0.1"
    
    def test_connection_selection(self):
        # Test that the controller selects appropriate connections
        bc = BMPController({})
        bc._scp_data_length = 128
        bc.connections = {
            (0, 0): Mock(),
            (0, 0, 1): Mock(),
            (0, 1, 1): Mock(),
        }
        
        # Use generic connection when that is all that's available
        bc.send_scp(0, cabinet=0, frame=0, board=0)
        bc.connections[(0, 0)].send_scp.assert_called_once_with(
            128, 0, 0, 0, 0)
        bc.connections[(0, 0)].send_scp.reset_mock()
        
        bc.send_scp(2, cabinet=0, frame=0, board=2)
        bc.connections[(0, 0)].send_scp.assert_called_once_with(
            128, 0, 0, 2, 2)
        bc.connections[(0, 0)].send_scp.reset_mock()
        
        
        # Use specific connection in preference to generic one
        bc.send_scp(1, cabinet=0, frame=0, board=1)
        bc.connections[(0, 0, 1)].send_scp.assert_called_once_with(
            128, 0, 0, 1, 1)
        bc.connections[(0, 0, 1)].send_scp.reset_mock()
        
        # Use a specific connection when that is all there is
        bc.send_scp(3, cabinet=0, frame=1, board=1)
        bc.connections[(0, 1, 1)].send_scp.assert_called_once_with(
            128, 0, 0, 1, 3)
        bc.connections[(0, 1, 1)].send_scp.reset_mock()
        
        # Fail with coordinates which can't be reached
        with pytest.raises(Exception):
            bc.send_scp(4, cabinet=0, frame=1, board=0)
        with pytest.raises(Exception):
            bc.send_scp(5, cabinet=1, frame=2, board=3)
    
    def test_get_software_version(self, bc_mock_sver, sver_response):
        # Test the sver command works.
        assert bc_mock_sver.get_software_version() == sver_response
    
    def test_scp_data_length(self, bc_mock_sver, sver_response):
        # Test the data length can be ascertained
        assert bc_mock_sver.scp_data_length == sver_response.buffer_size
