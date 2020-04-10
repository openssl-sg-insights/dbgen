# External
from typing import (
    Any,
    Set as S,
    List as L,
    Dict as D,
    Union as U,
    Callable as C,
)
from hypothesis.strategies import SearchStrategy, builds, lists, dictionaries

# Internal
from dbgen.core.fromclause import From
from dbgen.core.expr.expr import Expr, true, PK
from dbgen.core.expr.pathattr import PathAttr, expr_attrs
from dbgen.core.funclike import Arg
from dbgen.core.schema import RelTup, Obj
from dbgen.core.misc import ConnectInfo as ConnI
from dbgen.utils.lists import flatten, nub
from dbgen.utils.sql import select_dict
from dbgen.utils.misc import nonempty

"""
The Query class, as well as Ref (used to indirectly refer to an object in a
query without knowing the exact join path)

Furthermore some Model methods that are highly related to queries are defined.
"""

Fn = C[[Any], str]  # type shortcut

################################################################################
class Query(Expr):
    """
    Specification of a query, which can only be realized in the context of a model

    exprs - things you SELECT for, keys in dict are the aliases of the outputs
    basis - determines how many rows can possibly be in the output
            e.g. ['atom'] means one row per atom
                 ['element','struct'] means one row per (element,struct) pair
    constr - expression which must be evaluated as true in WHERE clause
    aconstr- expression which must be evaluated as true in HAVING clause
             (to do, automatically distinguish constr
             from aconstr by whether or not contains any aggs?)
    option - Objects which may or may not exist (i.e. LEFT JOIN on these)
    opt_attr - Attributes mentioned in query which may be null
            (otherwise NOT NULL constraint added to WHERE)
    """

    def __init__(
        self,
        exprs: D[str, Expr],
        basis: L[U[str, Obj]] = None,
        constr: Expr = None,
        aggcols: L[Expr] = None,
        aconstr: Expr = None,
        option: L[RelTup] = None,
        opt_attr: L[PathAttr] = None,
    ) -> None:
        err = "Expected %s, but got %s (%s)"
        for k, v in exprs.items():
            assert isinstance(k, str), err % ("str", k, type(k))
            assert isinstance(v, Expr), err % ("Expr", v, type(v))

        self.exprs = exprs
        self.aggcols = aggcols or []
        self.constr = constr or true
        self.aconstr = aconstr or None

        if not basis:
            attrobjs = nub([a.obj for a in self.allattr()], str)
            assert len(attrobjs) == 1, "Cannot guess basis for you %s" % attrobjs
            self.basis = attrobjs
        else:
            self.basis = [x if isinstance(x, str) else x.name for x in basis]

        self.option = option or []

        if opt_attr:
            for a in opt_attr:
                if isinstance(a, PK):
                    raise ValueError("You can' have an optional ID attrs currently")
                assert isinstance(a, PathAttr), err % ("PathAttr", a, type(a))
        self.opt_attr = opt_attr or []

    def __str__(self) -> str:
        return "Query<%d exprs>" % (len(self.exprs))

    def __getitem__(self, key: str) -> Arg:
        err = "%s not found in query exprs %s"
        assert key in self.exprs, err % (key, self.exprs)
        return Arg(self.hash, key)

    ####################
    # Abstract methods #
    ####################
    def show(self, f: Fn) -> str:
        """How to represent a Query as a subselect"""
        raise NotImplementedError

    def fields(self) -> L[Expr]:
        """Might be missing a few things here .... """
        return list(self.exprs.values())

    @classmethod
    def strat(cls) -> SearchStrategy:
        return builds(
            cls,
            exprs=dictionaries(keys=nonempty, values=Expr.strat()),
            basis=lists(nonempty, min_size=1, max_size=2),
            constr=Expr.strat(),
            aggcols=lists(Expr.strat(), max_size=2),
            aconstr=Expr.strat(),
            option=lists(RelTup.strat(), max_size=2),
            opt_attr=lists(PathAttr.strat(), max_size=2),
        )

    ####################
    # Public methods #
    ####################

    def allobj(self) -> L[str]:
        """All object names that are mentioned in query"""

        for a in self.allattr():
            if not hasattr(a, "obj"):
                print(a)
                import pdb

                pdb.set_trace()
        return (
            [o.obj for o in self.option] + self.basis + [a.obj for a in self.allattr()]
        )

    def allattr(self) -> S[PathAttr]:
        """All path+attributes that are mentioned in query"""
        agg_x = [expr_attrs(ac) for ac in self.aggcols]  # type: L[L[PathAttr]]
        es = list(self.exprs.values()) + [self.constr, self.aconstr or true]
        out = set(flatten([expr_attrs(expr) for expr in es] + agg_x))
        return out

    def allrels(self) -> S[RelTup]:
        """All relations EXPLICITLY mentioned in the query"""
        out = set(self.option)
        for a in self.allattr():
            out = out | a.allrels()
        return out

    ###################
    # Private methods #
    ###################
    def _make_from(self) -> From:
        """ FROM clause of a query - combining FROMs from all the Paths """
        f = From(self.basis)
        attrs = self.allattr()
        for a in attrs:
            f = f | a.path._from()
        return f

    def showQ(self) -> str:
        """
        Render a query

        To do: HAVING Clause
        """
        # FROM clause
        # ------------
        f = self._make_from()

        # What we select for
        # -------------------
        cols = ",\n\t".join(
            ['%s AS "%s"' % (e, k) for k, e in self.exprs.items()]  # .show(shower)
        )
        cols = "" + cols if cols else ""
        # WHERE and HAVING clauses
        # ---------------------------------
        # Aggregations refered to in WHERE are treated specially
        where = str(self.constr)  # self.show_constr({})
        notdel = "\n\t".join(
            ['AND NOT COALESCE("%s".deleted, False)' % o for o in f.aliases()]
        )
        notnul = "\n\t".join(
            [
                "AND %s IS NOT NULL" % (x)
                for x in self.allattr()
                if x not in self.opt_attr
            ]
        )
        consts = "WHERE %s" % ("\n\t".join([where, notdel, notnul]))

        # HAVING aggregations are treated 'normally'
        if self.aconstr:
            haves = "\nHAVING %s" % self.aconstr
        else:
            haves = ""

        # Group by clause, if anything SELECT'd has an aggregation
        # ---------------------------------------------------------
        def gbhack(x: Expr) -> str:
            """We want to take the CONCAT(PK," ",UID) exprs generated by Obj.id()
                and just replace them with PK"""
            if isinstance(x, PK):
                return str(x.pk)
            else:
                return str(x)

        gb = [gbhack(x) for x in self.aggcols]
        groupby = "\nGROUP BY %s" % (",".join(gb)) if gb else ""

        # Compute FROM clause
        # --------------------
        f_str = f.print(self.option)

        # Put everything together to make query string
        # ----------------------------------------------------
        fmt_args = [cols, f_str, consts, groupby, haves]
        output = "SELECT \n\t{0}\n{1}\n{2}{3}{4}".format(*fmt_args)

        return output

    def get_row_count(self, db: ConnI) -> int:
        prepend = """SELECT\n\tCOUNT(*)\nFROM ("""
        append = """\n) AS X"""
        statement = prepend + self.showQ() + append
        query_output = select_dict(db, statement)
        if query_output:
            row_count = query_output[0][0]
            return row_count
        raise ValueError(f"No query output for row_count query,\n{statement}")

    def exec_query(self, db: ConnI) -> L[dict]:
        """Execute a query object in a giving model using a database connection"""
        return select_dict(db, self.showQ())
