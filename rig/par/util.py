"""Utilities for common-case usage of place-and-route facilities.
"""

from collections import defaultdict

from six import iteritems

from ..machine import Cores


def build_application_map(vertices_applications, placements, allocation,
                          core_resource=Cores):
    """Build a mapping from application to a list of cores where the
    application is used.
    
    This utility function assumes that each vertex is associated with a
    specific application.
    
    Arguments
    ---------
    vertices_applications : {vertex: application, ...}
        Applications are represented by the path of their APLX file.
    placements : {vertex: (x, y), ...}
    allocation : {vertex: {resource: slice, ...}, ...}
        One of these resources should match the `core_resource` argument.
    core_resource : object
        The resource identifier which represents cores.
    
    Returns
    -------
    {application: {(x, y) : set([c, ...]), ...}, ...}
        For each application, for each used chip a set of core numbers onto
        which the application should be loaded.
    """
    application_map = defaultdict(lambda: defaultdict(set))
    
    for vertex, application in iteritems(vertices_applications):
        chip_cores = application_map[application][placements[vertex]]
        core_slice = allocation[vertex].get(core_resource, slice(0, 0))
        chip_cores.update(range(core_slice.start, core_slice.stop))
    
    return application_map
