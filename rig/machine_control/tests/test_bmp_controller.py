import pytest

import struct

from mock import Mock

from rig.machine_control import BMPController
from rig.machine_control.bmp_controller import BMPInfo
from rig.machine_control.packets import SCPPacket
from rig.machine_control.consts import SCPCommands, LEDAction, BMPInfoType, \
    BMP_V_SCALE_2_5, BMP_V_SCALE_3_3, BMP_V_SCALE_12, BMP_TEMP_SCALE, \
    BMP_MISSING_TEMP, BMP_MISSING_FAN

from rig.machine_control import consts


@pytest.fixture(scope="module")
def live_controller(bmp_ip):
    return BMPController(bmp_ip)


@pytest.fixture(scope="module")
def sver_response():
    return BMPInfo(code_block=1, frame_id=2, can_id=3, board_id=4,
                   version=123/100., buffer_size=512, build_date=1234,
                   version_string="Hello, World!")


@pytest.fixture(scope="module", params=["127.0.0.1", {(0, 0, 0): "127.0.0.1"}])
def bc_mock_sver(request, sver_response):
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

    bc = BMPController(request.param)
    bc._send_scp = Mock()
    bc._send_scp.return_value = Mock(spec_set=SCPPacket)
    bc._send_scp.return_value.arg1 = arg1
    bc._send_scp.return_value.arg2 = arg2
    bc._send_scp.return_value.arg3 = arg3
    bc._send_scp.return_value.data = \
        sver_response.version_string.encode("utf-8")

    return bc


@pytest.mark.order_id("bmp_hw_test")
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

    @pytest.mark.order_id("bmp_power_cycle")
    @pytest.mark.no_boot  # Don't run if booting is disabled
    def test_power_cycle(self, live_controller):
        # Power-cycle a board, also checks both types of board listings
        live_controller.set_power(False, board=0)
        live_controller.set_power(True, board=[0])

    def test_set_led(self, live_controller):
        # Toggle the LEDs
        live_controller.set_led(range(8), None)
        live_controller.set_led(range(8), None)

        # Control a single LED, explicitly
        live_controller.set_led(7, True)
        live_controller.set_led(7, False)

    @pytest.mark.order_after("bmp_power_cycle")
    def test_read_write_fpga_reg(self, live_controller):
        # The address of a read/writeable register in the FPGAs. This register
        # controls which packets are routed to external devices by the FPGA.
        # Since the mask defaults to 0s, setting this field to anything but a
        # zero value is safe. See the SpiNNaker FPGA design in the SpI/O
        # project for register definitions:
        # https://github.com/SpiNNakerManchester/spio
        PKEY_ADDR = 0x00040008

        # Write a value into the writeable peripheral multicast packet key
        # field of the FPGA and read it back
        for fpga_num in range(3):
            live_controller.write_fpga_reg(fpga_num, PKEY_ADDR,
                                           0xBEEF0000 | fpga_num)
        for fpga_num in range(3):
            assert live_controller.read_fpga_reg(fpga_num, PKEY_ADDR) == \
                0xBEEF0000 | fpga_num

    @pytest.mark.order_after("bmp_power_cycle")
    def test_read_adc(self, live_controller):
        # Read the ADC values and simply check they're within realistic ranges
        adc = live_controller.read_adc()
        assert 1.1 < adc.voltage_1_2a < 1.3 or -0.1 < adc.voltage_1_2a < 0.1
        assert 1.1 < adc.voltage_1_2b < 1.3 or -0.1 < adc.voltage_1_2b < 0.1
        assert 1.1 < adc.voltage_1_2c < 1.3 or -0.1 < adc.voltage_1_2c < 0.1
        assert 1.7 < adc.voltage_1_8 < 1.9 or -0.1 < adc.voltage_1_8 < 0.1
        assert 3.2 < adc.voltage_3_3 < 3.4 or -0.1 < adc.voltage_3_3 < 0.1
        assert 10.0 < adc.voltage_supply < 14.0
        assert 5.0 < adc.temp_top < 100.0
        assert 5.0 < adc.temp_btm < 100.0
        assert adc.temp_ext_0 is None or 5.0 < adc.temp_ext_0 < 100.0
        assert adc.temp_ext_1 is None or 5.0 < adc.temp_ext_1 < 100.0
        assert adc.fan_0 is None or 0.0 < adc.fan_0 < 10000.0
        assert adc.fan_1 is None or 0.0 < adc.fan_1 < 10000.0


@pytest.mark.order_after("spinnaker_hw_test", "bmp_hw_test")
@pytest.mark.no_boot  # Don't run if booting is disabled
def test_power_down_on_finished(live_controller):
    """Power down the system after testing is complete.

    The "order" marking on this test ensures that this test unit will run after
    all SpiNNaker hardware tests are complete.
    """
    live_controller.set_power(False, board=0)


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
            (1, 2, 3): Mock(),
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

        # Try using contexts
        with bc(cabinet=1, frame=2, board=3):
            bc.send_scp(4)
        bc.connections[(1, 2, 3)].send_scp.assert_called_once_with(
            128, 0, 0, 3, 4)
        bc.connections[(1, 2, 3)].send_scp.reset_mock()

        # Fail with coordinates which can't be reached
        with pytest.raises(Exception):
            bc.send_scp(5, cabinet=0, frame=1, board=0)
        with pytest.raises(Exception):
            bc.send_scp(6, cabinet=3, frame=2, board=1)

    def test_get_software_version(self, bc_mock_sver, sver_response):
        # Test the sver command works.
        assert bc_mock_sver.get_software_version() == sver_response

    def test_scp_data_length(self, bc_mock_sver, sver_response):
        # Test the data length can be ascertained (and remembered)
        assert bc_mock_sver.scp_data_length == sver_response.buffer_size
        assert bc_mock_sver.scp_data_length == sver_response.buffer_size

    def test_set_power(self):
        # Check power control of both one device and several to ensure that the
        # correct encoding is used.
        bc = BMPController("localhost")
        bc._send_scp = Mock()

        # Check single device and power down
        bc.set_power(False, 0, 0, 2)
        arg1 = 0 << 16 | 0
        arg2 = 1 << 2
        bc._send_scp.assert_called_once_with(
            0, 0, 2, SCPCommands.power,
            arg1=arg1, arg2=arg2, timeout=0.0, expected_args=0
        )
        bc._send_scp.reset_mock()

        # Check multiple device, power on and a delay
        bc.set_power(True, 0, 0, [1, 2, 4, 8], delay=0.1,
                     post_power_on_delay=0.0)
        arg1 = 100 << 16 | 1
        arg2 = (1 << 1) | (1 << 2) | (1 << 4) | (1 << 8)
        bc._send_scp.assert_called_once_with(
            0, 0, 1, SCPCommands.power,
            arg1=arg1, arg2=arg2, timeout=consts.BMP_POWER_ON_TIMEOUT,
            expected_args=0
        )

    @pytest.mark.parametrize("board,boards", [(0, [0]), (1, [1]), ([2], [2]),
                                              ([0, 1, 2], [0, 1, 2])])
    @pytest.mark.parametrize("action,led_action",
                             [(True, LEDAction.on), (False, LEDAction.off),
                              (None, LEDAction.toggle),
                              (None, LEDAction.toggle)])
    @pytest.mark.parametrize("led,leds", [(0, [0]), (1, [1]), ([2], [2]),
                                          ([0, 1, 2], [0, 1, 2])])
    def test_led_controls(self, board, boards, action, led_action, led, leds):
        """Check setting/clearing/toggling an LED.

        Outgoing:
            cmd_rc : 25
            arg1 : (on | off | toggle) << (led * 2)
        """
        # Create the mock controller
        bc = BMPController("localhost")
        bc._send_scp = Mock()

        # Perform the action
        bc.set_led(led, action, board=board)

        # Assert that there was 1 packet sent and that it was sane
        assert bc._send_scp.call_count == 1
        call, kwargs = bc._send_scp.call_args
        assert call == (0, 0, boards[0], SCPCommands.led)
        assert kwargs["arg1"] == sum(led_action << (led * 2) for led in leds)
        assert kwargs["arg2"] == sum(1 << b for b in boards)

    @pytest.mark.parametrize("addr,real_addr", [(0, 0), (1, 0), (4, 4)])
    @pytest.mark.parametrize("fpga_num", [0, 1, 2])
    def test_read_fpga_reg(self, addr, real_addr, fpga_num):
        # Check that register read commands are encoded validly and that
        # addresses are rounded appropriately
        bc = BMPController("localhost")
        bc._send_scp = Mock()
        bc._send_scp.return_value = Mock(spec_set=SCPPacket)
        bc._send_scp.return_value.data = struct.pack("<I", 0xDEADBEEF)

        assert bc.read_fpga_reg(fpga_num, addr) == 0xDEADBEEF
        arg1 = real_addr
        arg2 = 4
        arg3 = fpga_num
        bc._send_scp.assert_called_once_with(
            0, 0, 0, SCPCommands.link_read,
            arg1=arg1, arg2=arg2, arg3=arg3, expected_args=0
        )

    @pytest.mark.parametrize("addr,real_addr", [(0, 0), (1, 0), (4, 4)])
    @pytest.mark.parametrize("fpga_num", [0, 1, 2])
    def test_write_fpga_reg(self, addr, real_addr, fpga_num):
        # Check that register write commands are encoded validly and that
        # addresses are rounded appropriately
        bc = BMPController("localhost")
        bc._send_scp = Mock()

        bc.write_fpga_reg(fpga_num, addr, 0xDEADBEEF)
        arg1 = real_addr
        arg2 = 4
        arg3 = fpga_num
        bc._send_scp.assert_called_once_with(
            0, 0, 0, SCPCommands.link_write,
            arg1=arg1, arg2=arg2, arg3=arg3,
            data=struct.pack("<I", 0xDEADBEEF),
            expected_args=0
        )

    @pytest.mark.parametrize("t_ext0,t_ext0_raw",
                             [(35.0, int(35.0 / BMP_TEMP_SCALE)),
                              (None, BMP_MISSING_TEMP)])
    @pytest.mark.parametrize("t_ext1,t_ext1_raw",
                             [(25.0, int(25.0 / BMP_TEMP_SCALE)),
                              (None, BMP_MISSING_TEMP)])
    @pytest.mark.parametrize("fan_0,fan_0_raw",
                             [(1000, 1000),
                              (None, BMP_MISSING_FAN)])
    @pytest.mark.parametrize("fan_1,fan_1_raw",
                             [(1000, 1000),
                              (None, BMP_MISSING_FAN)])
    def test_read_adc(self, t_ext0, t_ext0_raw, t_ext1, t_ext1_raw,
                      fan_0, fan_0_raw, fan_1, fan_1_raw):
        # Generate fake ADC data and check that it is decoded correctly
        bc = BMPController("localhost")
        bc._send_scp = Mock()
        bc._send_scp.return_value = Mock(spec_set=SCPPacket)
        bc._send_scp.return_value.data = \
            struct.pack("<"   # Little-endian
                        "8H"  # uint16_t adc[8]
                        "4h"  # int16_t t_int[4]
                        "4h"  # int16_t t_ext[4]
                        "4h"  # int16_t fan[4]
                        "I"   # uint32_t warning
                        "I",  # uint32_t shutdown
                        0,                           # adc[0] Unused
                        int(1.1 / BMP_V_SCALE_2_5),  # adc[1] 1.2 V (C)
                        int(1.2 / BMP_V_SCALE_2_5),  # adc[2] 1.2 V (B)
                        int(1.3 / BMP_V_SCALE_2_5),  # adc[3] 1.2 V (A)
                        int(1.8 / BMP_V_SCALE_2_5),  # adc[4] 1.8 V
                        0,                           # adc[5] Unused
                        int(3.3 / BMP_V_SCALE_3_3),  # adc[6] 3.3 V
                        int(12.0 / BMP_V_SCALE_12),  # adc[7] 12.0 V
                        int(40.0 / BMP_TEMP_SCALE),  # t_int[0] 40 *C
                        int(30.0 / BMP_TEMP_SCALE),  # t_int[1] 30 *C
                        0,                           # t_int[2] Unused
                        0,                           # t_int[3] Unused
                        t_ext0_raw,                  # t_ext[0]
                        t_ext1_raw,                  # t_ext[1]
                        0,                           # t_ext[2] Unused
                        0,                           # t_ext[3] Unused
                        fan_0_raw,                   # fan[0]
                        fan_1_raw,                   # fan[1]
                        0,                           # fan[2] Unused
                        0,                           # fan[3] Unused
                        0,                           # warning (unused)
                        0)                           # shutdown (unused)

        adc = bc.read_adc()
        bc._send_scp.assert_called_once_with(
            0, 0, 0, SCPCommands.bmp_info,
            arg1=BMPInfoType.adc,
            expected_args=0
        )

        # Fuzzy float test
        assert abs(adc.voltage_1_2a - 1.3) < 0.01
        assert abs(adc.voltage_1_2b - 1.2) < 0.01
        assert abs(adc.voltage_1_2c - 1.1) < 0.01
        assert abs(adc.voltage_1_8 - 1.8) < 0.01
        assert abs(adc.voltage_3_3 - 3.3) < 0.01
        assert abs(adc.voltage_supply - 12.0) < 0.01
        assert abs(adc.temp_top - 40.0) < 0.01
        assert abs(adc.temp_btm - 30.0) < 0.01

        # Test if None when the expected value is, otherwise fuzzy float test
        assert adc.temp_ext_0 is t_ext0 or abs(adc.temp_ext_0 - t_ext0) < 0.01
        assert adc.temp_ext_1 is t_ext1 or abs(adc.temp_ext_1 - t_ext1) < 0.01
        assert adc.fan_0 is fan_0 or abs(adc.fan_0 - fan_0) < 0.01
        assert adc.fan_1 is fan_1 or abs(adc.fan_1 - fan_1) < 0.01
