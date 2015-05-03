import six
from ..machine import Cores, SDRAM


def sdram_alloc_for_vertices(controller, placements, allocations,
                             core_as_tag=True, buffer_size=0,
                             sdram_resource=SDRAM, cores_resource=Cores):
    """Allocate and return a file-like view of a region of SDRAM for each
    vertex which uses SDRAM as a resource.

    The tag assigned to each region of assigned SDRAM is the index of the
    first core that each vertex is assigned.  For example::

        placements = {vertex: (0, 5)}
        allocations = {vertex: {Cores: slice(3, 6),
                                SDRAM: slice(204, 304)}}
        sdram_allocations = sdram_alloc_for_vertices(
            controller, placements, allocations
        )

    Will allocate a 100-byte block of SDRAM for the vertex which is
    allocated cores 3-5 on chip (0, 5).  The region of SDRAM will be tagged
    `3` (because this is the index of the first core).

    Parameters
    ----------
    controller : :py:class:`rig.machine_control.MachineController`
        Controller to use to allocate the SDRAM.
    placements : {vertex: (x, y), ...}
        Mapping of vertices to the chips they have been placed on.  Same as
        produced by placers.
    allocations : {vertex: {resource: allocation, ...}, ...}
        Mapping of vertices to the resources they have been allocated.

        A block of memory of the size specified by the `sdram_resource`
        (default: :py:class:`~rig.machine.SDRAM`) resource will be allocated
        for each vertex. Note that location of the supplied allocation is *not*
        used.

        When `core_as_tag=True`, the tag allocated will be the ID of the first
        core used by the vertex (indicated by the `cores_resource`, default
        :py:class:`~rig.machine.Cores`), otherwise the tag will be set to 0.

    Other Parameters
    ----------------
    core_as_tag : bool
        Use the index of the first allocated core as the tag for the region of
        memory, otherwise 0 will be used.
    buffer_size : int
        Size of write buffer (in bytes) to allocate to _each_ file-like object
        created by this method.
    sdram_resource : resource (default :py:class:`~rig.machine.SDRAM`)
        Key used to indicate SDRAM usage in the resources dictionary.
    cores_resource : resource (default :py:class:`~rig.machine.Cores`)
        Key used to indicate cores which have been allocated in the
        allocations dictionary.

    Returns
    -------
    {vertex: :py:class:`.MemoryIO`, ...}
        A file-like object for each vertex which can be used to read and write
        to the region of SDRAM allocated to the vertex.

    Raises
    ------
    SpiNNakerMemoryError
        If the memory cannot be allocated, or a tag is already taken or
        invalid.
    """
    # For each vertex we perform an SDRAM alloc to get a file-like for
    # the vertex.
    vertex_memory = dict()
    for vertex, allocs in six.iteritems(allocations):
        if sdram_resource in allocs:
            sdram_slice = allocs[sdram_resource]
            assert sdram_slice.step is None

            size = sdram_slice.stop - sdram_slice.start
            x, y = placements[vertex]

            if core_as_tag:
                tag = allocs[cores_resource].start
            else:
                tag = 0

            # Get the memory
            vertex_memory[vertex] = controller.sdram_alloc_as_filelike(
                size, tag, x=x, y=y, buffer_size=buffer_size
            )

    return vertex_memory
