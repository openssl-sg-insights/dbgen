#   Copyright 2021 Modelyst LLC
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from pprint import pformat
from typing import List

from networkx import DiGraph, NetworkXUnfeasible
from networkx.algorithms import lexicographical_topological_sort, simple_cycles


# Graph
# --------
def topsort_with_dict(G: DiGraph) -> List:
    """
    Assuming a graph with object names and dict mapping names to objects,
    perform a topsort and return the list of objects.
    """
    try:
        sortd = list(lexicographical_topological_sort(G))
        return sortd
    except NetworkXUnfeasible:
        cycles = pformat(list(simple_cycles(G)))
        raise ValueError(f"Cycles found: {cycles}")
