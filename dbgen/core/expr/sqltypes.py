# External Modules
from typing import Any
from abc import abstractmethod, ABCMeta
from re import split
from random import choice
from string import ascii_lowercase, ascii_uppercase, digits
from hypothesis.strategies import SearchStrategy, from_type  # type: ignore

from dbgen.utils.misc import Base

"""
Representations of SQL Data Types
"""
################################################################################
chars = ascii_lowercase + ascii_uppercase + digits


class SQLType(Base, metaclass=ABCMeta):
    """
    SQL datatypes
    """

    data = {}  # type: dict

    @classmethod
    def strat(cls) -> SearchStrategy:
        return from_type(cls)

    @abstractmethod
    def __str__(self) -> str:
        """String representation to be used in raw SQL expression"""
        raise NotImplementedError

    def __init__(self) -> None:
        pass

    @staticmethod
    def from_str(s: str) -> "SQLType":
        """
        Ad hoc string parsing
        """
        if "VARCHAR" in s:
            mem = split(r"\(|\)", s)[1]
            return Varchar(int(mem))
        elif "DECIMAL" in s:
            prec, scale = split(r"\(|\)|,", s)[1:3]
            return Decimal(int(prec), int(scale))
        elif "INT" in s:
            if "TINY" in s:
                kind = "tiny"
            elif "BIG" in s:
                kind = "big"
            else:
                kind = "medium"
            signed = "UNSIGNED" not in s
            return Int(kind, signed)
        elif "TEXT" in s:
            if "TINY" in s:
                kind = "tiny"
            elif "MED" in s:
                kind = "medium"
            elif "LONG" in s:
                kind = "long"
            else:
                kind = ""
            return Text(kind)
        else:
            raise NotImplementedError("New SQLtype to parse? " + s)


class Varchar(SQLType):
    def __init__(self, mem: int = 255) -> None:
        self.mem = mem

    def __str__(self) -> str:
        return "VARCHAR(%d)" % self.mem


class Decimal(SQLType):
    def __init__(self, prec: int = 15, scale: int = 6) -> None:
        self.prec = prec
        self.scale = scale

    def __str__(self) -> str:
        return "DECIMAL(%d,%d)" % (self.prec, self.scale)


class Boolean(SQLType):
    def __init__(self) -> None:
        pass

    def __str__(self) -> str:
        return "Boolean"

    def rand(self) -> Any:
        return choice(["true", "false"])


class Int(SQLType):
    def __init__(self, kind: str = "medium", signed: bool = True) -> None:
        kinds = ["small", "medium", "big"]
        assert kind in kinds, "Invalid Int type: %s not found in %s" % (kind, kinds)
        self.kind = kind
        self.signed = signed

    def __str__(self) -> str:
        options = ["small", "medium", "big"]
        if self.kind == "small":
            core = "SMALLINT"
        elif self.kind == "medium":
            core = "INTEGER"
        elif self.kind == "big":
            core = "BIGINT"
        else:
            err = 'unknown Int kind "%s" not in options %s '
            raise ValueError(err % (self.kind, options))
        return core + ("" if self.signed else " UNSIGNED")


class Text(SQLType):
    def __init__(self, kind: str = "") -> None:
        self.kind = kind

    def __str__(self) -> str:
        return "TEXT"


class Date(SQLType):
    def __str__(self) -> str:
        return "DATE"


class Timestamp(SQLType):
    def __str__(self) -> str:
        return "TIMESTAMP"


class Double(SQLType):
    def __str__(self) -> str:
        return "DOUBLE"


class JSON(SQLType):
    def __str__(self) -> str:
        return "JSON"


class JSONB(SQLType):
    def __str__(self) -> str:
        return "JSONB"