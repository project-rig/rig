"""Generate app_ptr tables for data stored in SDRAM.
"""
import struct


def create_app_ptr_table(regions, vertex_slice=slice(0, 1),
                         magic_num=0xAD130AD6, version=0x00010000,
                         timer_period=1000):
    """Create a bytestring representing the application pointer table
    indicating the location of regions in SDRAM.

    Parameters
    ----------
    regions : dict
        A mapping on integers to `rig.regions.Region` instances that are to be
        stored in memory.  The integer is the "number" of the region.
    vertex_slice : :py:func:`slice`
        The slice that should be applied to each region.  In the case of
        unsliced regions this may be left with its default value.
    magic_num : int
    version : int
    timer_period : int

    Returns
    -------
    bytestring
        A string of bytes which should be written into memory immediately
        before any region data.
    """
    # Pack the header data
    header = [magic_num, version, timer_period]

    # Add region offsets
    max_index = 0
    table = []
    if len(regions) > 0:
        max_index = max(sorted(regions.keys())) + 1
        table = [0] * max_index
        offset = (max_index + len(header)) * 4

    for index in sorted(regions.keys()):
        # Set the offset for this region
        table[index] = offset

        # Then increment to account for the data stored in this region
        offset += regions[index].sizeof(vertex_slice)

        # Progress to the next word boundary
        offset += (4 - (offset & 0x3)) & 0x3

    return struct.pack('<' + 'I' * (max_index + len(header)),
                       *(header + table))
