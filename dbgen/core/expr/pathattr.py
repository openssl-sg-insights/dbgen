from typing import Any, Set as S, List as L, Optional as Opt, Callable as C
from hypothesis.strategies import SearchStrategy, builds, none, from_type  # type: ignore

from dbgen.core.schema import AttrTup, RelTup
from dbgen.core.expr.expr import Expr
from dbgen.core.fromclause import Path
from dbgen.utils.lists import flatten

Fn = C[[Any], str]  # type shortcut

########################
class PathAttr(Expr):
    def __init__(self, path: Opt[Path], attr: AttrTup) -> None:
        assert attr
        self.path = path or Path(attr.obj)
        self.attr = attr

    def __str__(self) -> str:
        return '"%s"."%s"' % (self.path, self.attr.name)

    def __repr__(self) -> str:
        return "PathAttr<%s.%s>" % (self.path, self.attr)

    @classmethod
    def strat(cls) -> SearchStrategy:
        return builds(cls, path=none(), attr=from_type(AttrTup))

    ####################
    # Abstract methods #
    ####################
    def attrs(self) -> L["PathAttr"]:
        return [self]

    def fields(self) -> list:
        """
        List of immediate substructures of the expression (not recursive)
        """
        return []

    def show(self, f: Fn) -> str:
        """Apply function recursively to fields."""
        return f(self)

    @property
    def name(self) -> str:
        return self.attr.name

    @property
    def obj(self) -> str:
        return self.attr.obj

    def allrels(self) -> S[RelTup]:
        stack = list(self.path.fks)
        rels = set()
        while stack:
            curr = stack.pop(0)
            if not isinstance(curr, list):
                rels.add(curr.tup())
            else:
                assert not stack  # only the last element should be a list
                stack = flatten(curr)
        return rels


################################################################################
def expr_attrs(expr: Expr) -> L["PathAttr"]:
    """Recursively search for any Path (Expr) mentions in the Expr."""
    out = [expr] if isinstance(expr, PathAttr) else []  # type: L['PathAttr']
    if hasattr(expr, "fields"):
        for field in expr.fields():
            out.extend(expr_attrs(field))

    return out