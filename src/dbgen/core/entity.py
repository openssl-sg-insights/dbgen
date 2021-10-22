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

from datetime import datetime
from functools import partial
from io import StringIO
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)
from uuid import UUID

from pydantic import root_validator
from sqlalchemy import Column, DateTime
from sqlalchemy.orm import registry
from sqlalchemy.sql import func
from sqlalchemy.sql.base import ImmutableColumnCollection
from sqlalchemy.sql.schema import Table
from sqlmodel.main import Field, FieldInfo, SQLModel, SQLModelMetaclass

from dbgen.core.args import ArgLike
from dbgen.core.base import Base, BaseMeta
from dbgen.core.node.load import Load, LoadEntity
from dbgen.exceptions import DBgenInvalidArgument, DBgenMissingInfo


def inherit_field(bases, field_name: str, initial_value=set(), joiner=lambda x, y: x.union(y)):
    field_val = initial_value
    for base in reversed(bases):
        curr_id = getattr(base, field_name, initial_value)
        if curr_id is not None:
            assert isinstance(curr_id, type(initial_value)), f"Invalid {field_name} val: {curr_id}"
            field_val = joiner(field_val, curr_id)
    return field_val


overwrite_parent = partial(inherit_field, initial_value="", joiner=lambda x, y: y)
DEFAULT_ENTITY_REGISTRY = registry()


_T = TypeVar("_T")


def __dataclass_transform__(
    *,
    eq_default: bool = True,
    order_default: bool = False,
    kw_only_default: bool = False,
    field_descriptors: Tuple[Union[type, Callable[..., Any]], ...] = (()),
) -> Callable[[_T], _T]:
    return lambda a: a


@__dataclass_transform__(
    kw_only_default=True,
    field_descriptors=(
        Field,
        FieldInfo,
    ),
)
class EntityMetaclass(SQLModelMetaclass, BaseMeta):
    def __new__(mcs, name, bases, attrs, **kwargs):
        # Join the keys from all parents for __identifying__, _hashinclude_, and _hashexclude_
        new_attrs = attrs.copy()
        for field in ("__identifying__", "_hashexclude_", "_hashinclude_"):
            starting = new_attrs.get(field, set())
            new_attrs[field] = starting.union(inherit_field(bases, field))

        if kwargs.get('all_id', False):
            assert (
                "__identifying__" not in attrs
            ), f"Error with Entity {name}. Can't supply both all_id kwarg and __identifying__ attr"
            new_attrs['__identifying__'] = new_attrs['__identifying__'].union(
                {key for key in attrs.get('__annotations__', {})}
            )
        # Automatically add identifying attributes to the hashinclude
        new_attrs["_hashinclude_"].update(new_attrs.get("__identifying__"))
        # Set the default registry to be the default_registry
        if "registry" not in kwargs:
            kwargs["registry"] = DEFAULT_ENTITY_REGISTRY
        cls = super().__new__(mcs, name, bases, new_attrs, **kwargs)
        # Validate that we don't have table=True on current class and a base
        current_cls_is_table = getattr(cls.__config__, "table", False) and kwargs.get("table")
        setattr(cls, "_is_table", current_cls_is_table)

        if current_cls_is_table:
            base_is_table = False
            for base in bases:
                config = getattr(base, "__config__", None)
                if config and getattr(config, "table", False):
                    base_is_table = True
                    offending_base_name = base.__name__
                    break
            if base_is_table:
                raise ValueError(
                    "Can't use table=True when inheriting from another table.\n"
                    f"Both {offending_base_name} and {name} have table=True set.\n"
                    "Create a common ancestor with table=False and mutaually inherit from that."
                )
        # Need to look into parents to find schema, only using most recent
        schema_key = "__schema__"
        schema = getattr(cls, schema_key, "") or overwrite_parent(bases, schema_key)
        table_args = getattr(cls, "__table_args__", None) or dict().copy()
        if not schema:
            schema = "public"
        if schema:
            setattr(cls, schema_key, schema)
            table_args = table_args.copy()
            table_args.update({"schema": schema})

        setattr(cls, "__table_args__", table_args)
        setattr(
            cls,
            "__fulltablename__",
            f"{schema}.{cls.__tablename__}" if schema else cls.__tablename__,
        )
        # Validate __identifying__ by making sure all attribute exists on Entity
        unknown_ids = list(
            filter(
                lambda x: x not in cls.__fields__,
                new_attrs["__identifying__"],
            )
        )
        if unknown_ids:
            raise ValueError(
                f"Invalid Entity Class Definition. Identifying attributes not found on class: {unknown_ids}"
            )
        return cls

    def __init__(cls, name, bases, attrs, **kwargs):
        if cls._is_table:
            registry = cls._sa_registry
            if cls.__fulltablename__ in registry.metadata.tables:
                raise ValueError(
                    f"The Class {attrs.get('__module__','')}.{name}'s __table_name__ {cls.__tablename__!r} already present in the registry's metadata.\n"
                    "This can occur if two Entity sub-classes share a case-insensitive name or if the same table has been added to the registry twice.\n"
                    "To address this you can set a different __tablename__ attribute for one or to clear the registry, you can call Entity.clear_registry() prior to declaring this class."
                )
        super().__init__(name, bases, attrs, **kwargs)


class BaseEntity(Base, SQLModel, metaclass=EntityMetaclass):
    __identifying__: ClassVar[Set[str]]
    __fulltablename__: ClassVar[str]
    __schema__: ClassVar[str]
    __table__: ClassVar[Table]
    _is_table: ClassVar[bool]
    _sa_registry: ClassVar[registry]

    class Config:
        """Pydantic Config"""

        force_validation = True

    @classmethod
    def _columns(cls) -> ImmutableColumnCollection:
        if isinstance(cls.__fulltablename__, str):
            table = cls.metadata.tables.get(cls.__fulltablename__)
            if table is not None:
                return table.c
            raise ValueError(
                f"{cls.__fulltablename__} not in metadata, is table=True set? {cls.metadata.tables}"
            )
        raise ValueError(f"Can't read __fulltablename__ {cls.__fulltablename__}")

    @classmethod
    def _get_load_entity(cls) -> LoadEntity:
        """Returns a LoadEntity which has the bare-minimum needed to load into this table."""
        # Check that entity is a table
        if not cls._is_table:
            raise ValueError(f"{cls.__qualname__} is not a table. Can't get LoadEntity of a non-table Entity")
        columns = cls._columns()
        # Search for primary key name
        primary_keys = [x.name for x in cls.__table__.primary_key]
        if len(primary_keys) > 1:
            raise NotImplementedError(f"Multiple primary_keys found: {primary_keys}")
        elif not primary_keys:
            raise ValueError(f"No primary key found on {cls.__name__}'s columns:\n{columns}")
        primary_key_name = primary_keys[0]
        all_attrs = {col.name: col for col in columns if not col.foreign_keys}
        all_fks = {col.name: col for col in columns if col.foreign_keys}
        identifying_attributes = {
            x: cls.__fields__[x].type_.__name__ for x in all_attrs if x in cls.__identifying__
        }
        identifying_fks = [x for x in all_fks if x in cls.__identifying__]
        return LoadEntity(
            name=cls.__tablename__,
            schema_=cls.__schema__,
            primary_key_name=primary_key_name,
            identifying_attributes=identifying_attributes,
            identifying_foreign_keys=identifying_fks,
        )

    @classmethod
    def load(cls, insert: bool = False, **kwargs) -> Load:
        name = cls.__tablename__
        assert isinstance(name, str)
        key_filter = lambda keyval: keyval[0] != "insert" and not isinstance(keyval[1], (ArgLike, Load))
        invalid_args = list(filter(key_filter, kwargs.items()))
        if invalid_args:
            raise ValueError(f"Non ArgLike kwargs provided: {invalid_args}")

        # get PK
        pk = kwargs.pop(name, None)
        # if we don't have a PK reference check for missing ID info
        if not pk:
            missing = cls.__identifying__ - set(kwargs)
            if missing:
                err = (
                    "Cannot refer to a row in {} without a PK or essential data."
                    " Missing essential data: {}"
                )
                raise DBgenMissingInfo(err.format(name, missing))

        # Iterate through the columns to ensure we have no unknown kwargs
        class_columns: List[Column] = list(cls._columns()) or []
        all_attrs = {col.name: col for col in class_columns if not col.foreign_keys}
        all_fks = {col.name: col for col in class_columns if col.foreign_keys}
        attrs = {key: val for key, val in kwargs.items() if key in all_attrs}
        fks = {key: col for key, col in kwargs.items() if key not in attrs}
        for fk in fks:
            if fk not in all_fks:
                raise DBgenInvalidArgument(f'unknown "{fk}" kwarg in Load of {name}')

        for k, v in fks.items():
            if isinstance(v, Load):
                fks[k] = v["out"]

        return Load(
            load_entity=cls._get_load_entity(),
            primary_key=pk,
            inputs={**attrs, **fks},
            insert=insert,
        )

    @classmethod
    def _quick_load(cls, connection, rows: Iterable[Iterable[Any]], column_names: List[str]) -> None:
        """Bulk load many rows into entity"""
        from dbgen.templates import jinja_env

        # Assemble rows into stringio for copy_from statement
        io_obj = StringIO()
        for row in rows:
            io_obj.write("\t".join(map(str, row)) + "\n")
        io_obj.seek(0)

        # Temporary table to copy data into
        # Set name to be hash of input rows to ensure uniqueness for parallelization
        temp_table_name = f"{cls.__tablename__}_temp_load_table"

        load_entity = cls._get_load_entity()
        # Need to create a temp table to copy data into
        # Add an auto_inc column so that data can be ordered by its insert location
        drop_temp_table = f"DROP TABLE IF EXISTS {temp_table_name};"
        create_temp_table = """
        CREATE TEMPORARY TABLE {temp_table_name} AS
        TABLE {schema}.{obj}
        WITH NO DATA;
        ALTER TABLE {temp_table_name}
        ADD COLUMN auto_inc SERIAL NOT NULL;
        """.format(
            obj=load_entity.name,
            schema=load_entity.schema_,
            temp_table_name=temp_table_name,
        )

        insert_template = jinja_env.get_template("insert.sql.jinja")
        template_args = dict(
            obj=load_entity.name,
            obj_pk_name=load_entity.primary_key_name,
            temp_table_name=temp_table_name,
            all_column_names=column_names,
            schema=load_entity.schema_,
            first=False,
            update=True,
        )
        insert_statement = insert_template.render(**template_args)
        with connection.cursor() as curs:
            curs.execute(drop_temp_table)
        connection.commit()
        with connection.cursor() as curs:
            curs.execute(create_temp_table)
            curs.copy_from(io_obj, temp_table_name, null="None", columns=column_names)
            curs.execute(insert_statement)
        connection.commit()
        with connection.cursor() as curs:
            curs.execute(drop_temp_table)
        connection.commit()

    @classmethod
    def clear_registry(cls):
        """Removes all Entity classes from the Entity registry"""
        cls.metadata.clear()
        cls._sa_registry.dispose()

    @classmethod
    def foreign_key(cls, primary_key: bool = False):
        """Removes all Entity classes from the Entity registry"""
        load_entity = cls._get_load_entity()
        return Field(
            None,
            foreign_key=f"{cls.__fulltablename__}.{load_entity.primary_key_name}",
            primary_key=primary_key,
        )


id_field = Field(
    default=None,
    primary_key=True,
    sa_column_kwargs={"autoincrement": False, "unique": True},
)
gen_id_field = Field(
    default=None,
)

get_created_at_field = lambda: Field(
    None, sa_column=Column(DateTime(timezone=True), server_default=func.now())
)


class Entity(BaseEntity):
    id: Optional[UUID] = id_field
    gen_id: Optional[UUID]
    created_at: Optional[datetime] = get_created_at_field()

    @root_validator
    def _get_id(cls, values):
        if cls._is_table:
            load_entity = cls._get_load_entity()
            values["id"] = load_entity._get_hash(values)
        return values


Model = TypeVar("Model", bound="BaseEntity")


@overload
def create_entity(
    model_name: str,
    field_definitions: Dict[str, Union[Tuple[type, Any], type, Tuple[type, ...]]],
    base: None = None,
    identifying: Set[str] = None,
    schema: Optional[str] = None,
    __module__: str = __name__,
    **kwargs,
) -> Type[BaseEntity]:
    ...


@overload
def create_entity(
    model_name: str,
    field_definitions: Dict[str, Union[Tuple[type, Any], type, Tuple[type, ...]]],
    base: Type[Model],
    identifying: Set[str] = None,
    schema: Optional[str] = None,
    __module__: str = __name__,
    **kwargs,
) -> Type[Model]:
    ...


def create_entity(
    model_name: str,
    field_definitions: Dict[str, Union[Tuple[type, Any], type, Tuple[type, ...]]] = None,
    base: Optional[Type[Model]] = None,
    identifying: Set[str] = None,
    schema: Optional[str] = None,
    __module__: str = __name__,
    **kwargs,
) -> Type[Model]:
    """
    Dynamically create a model, similar to the Pydantic `create_model()` method
    :param model_name: name of the created model
    :param field_definitions: data fields of the create model
    :param base: base to inherit from
    :param __module__: module of the created model
    :param **kwargs: Other keyword arguments to pass to the metaclass constructor, e.g. table=True
    """

    if base is None:
        base = cast(Type["Model"], BaseEntity)
    field_definitions = field_definitions or {}

    fields = {}
    annotations = {}
    identifying = identifying or set()

    for f_name, f_def in field_definitions.items():
        if f_name.startswith("_"):
            raise ValueError("Field names may not start with an underscore")
        try:
            if isinstance(f_def, tuple) and len(f_def) > 1:
                f_annotation, f_value = f_def
            elif isinstance(f_def, tuple):
                f_annotation, f_value = f_def[0], Field(nullable=False)
            else:
                f_annotation, f_value = f_def, Field(nullable=False)
        except ValueError as e:
            raise ValueError(
                "field_definitions values must be either a tuple of (<type_annotation>, <default_value>)"
                "or just a type annotation [or a 1-tuple of (<type_annotation>,)]"
            ) from e

        if f_annotation:
            annotations[f_name] = f_annotation
        fields[f_name] = f_value

    namespace = {
        "__annotations__": annotations,
        "__identifying__": identifying,
        "__module__": __module__,
    }
    if schema is not None:
        namespace.update({"__schema__": schema})
    if "registry" in kwargs:
        assert isinstance(kwargs.get("registry"), registry), "Invalid type for registry:"
    namespace.update(fields)  # type: ignore

    return EntityMetaclass(model_name, (base,), namespace, **kwargs)