import mock
import pytest
import struct
from ..app_ptr import create_app_ptr_table


@pytest.mark.parametrize(
    "magic_num, version, timer_period",
    [(0xAD130AD6, 0x12341234, 1000),
     (0xFFFFAAAA, 0x00001000, 1234)])
def test_create_app_ptr_no_regions(magic_num, version, timer_period):
    """Creating an application pointer table with no regions should just write
    out header.
    """
    assert (create_app_ptr_table({}, magic_num=magic_num, version=version,
                                 timer_period=timer_period) ==
            struct.pack('3I', magic_num, version, timer_period))


def test_create_app_ptr():
    """Create a app_ptr table with entries of different sizes and with missing
    regions.
    """
    # Region 0 -> doesn't align on words
    r0 = mock.Mock(name="region 0", spec_set=['sizeof'])
    r0.sizeof.return_value = 3

    # Region 1 is missing

    # Region 2 is missing

    # Region 3 -> 75 words
    r3 = mock.Mock(name="region 3", spec_set=['sizeof'])
    r3.sizeof.return_value = 75 * 4

    # Region 4 -> 2 bytes
    r4 = mock.Mock(name="region 4", spec_set=['sizeof'])
    r4.sizeof.return_value = 2

    # Region 5 -> 1 bytes
    r5 = mock.Mock(name="region 5", spec_set=['sizeof'])
    r5.sizeof.return_value = 1

    # Create the region dictionary
    regions = {0: r0, 3: r3, 4: r4, 5: r5}

    # Get the app pointer table
    sl = mock.Mock(name="slice")
    table = create_app_ptr_table(regions, sl)

    # Check the length of the table
    assert len(table) == (3 + 6) * 4  # 3 header words, 5 regions

    # Region 0 should be offset 36 bytes
    assert table[12:16] == struct.pack('<I', 36)

    # Neither region 1 or 2 exist
    assert (table[16:20] == b'\x00' * 4) or (table[16:20] == b'\xff' * 4)
    assert (table[20:24] == b'\x00' * 4) or (table[20:24] == b'\xff' * 4)

    # Region 3 should be offset 36 + 3 + 1 bytes (40)
    assert table[24:28] == struct.pack('<I', 40)

    # Region 4 should be offset 40 + 300 bytes
    assert table[28:32] == struct.pack('<I', 340)

    # Region 5 should be offset 340 + 4 bytes
    assert table[32:36] == struct.pack('<I', 344)

    # Check each region was called with the same vertex slice
    for r in (r0, r3, r4, r5):
        r.sizeof.assert_called_once_with(sl)
