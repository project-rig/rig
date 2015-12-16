from rig.routing_table.entries import RoutingTableEntry, Routes
from rig.routing_table.exceptions import MinimisationFailedError
from rig.routing_table.utils import table_is_subset_of, expand_entries

# Next line chooses the default routing table minimiser
from rig.routing_table.ordered_covering import minimise
