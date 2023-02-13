"""Plugin that provides support for dataclasses."""

from __future__ import annotations

from typing import Optional
from typing_extensions import Final

from mypy import errorcodes, message_registry
from mypy.expandtype import expand_type
from mypy.nodes import (
    ARG_NAMED,
    ARG_NAMED_OPT,
    ARG_OPT,
    ARG_POS,
    ARG_STAR,
    ARG_STAR2,
    MDEF,
    Argument,
    AssignmentStmt,
    CallExpr,
    ClassDef,
    Context,
    DataclassTransformSpec,
    Expression,
    JsonDict,
    NameExpr,
    Node,
    PlaceholderNode,
    RefExpr,
    Statement,
    SymbolTableNode,
    TempNode,
    TypeAlias,
    TypeInfo,
    TypeVarExpr,
    Var,
)
from mypy.plugin import ClassDefContext, SemanticAnalyzerPluginInterface
from mypy.plugins.common import (
    _get_decorator_bool_argument,
    add_attribute_to_class,
    add_method_to_class,
    deserialize_and_fixup_type,
)
from mypy.semanal_shared import find_dataclass_transform_spec
from mypy.server.trigger import make_wildcard_trigger
from mypy.state import state
from mypy.typeops import map_type_from_supertype
from mypy.types import (
    AnyType,
    CallableType,
    Instance,
    LiteralType,
    NoneType,
    TupleType,
    Type,
    TypeOfAny,
    TypeVarType,
    get_proper_type,
)
from mypy.typevars import fill_typevars

# The set of decorators that generate dataclasses.
dataclass_makers: Final = {"dataclass", "dataclasses.dataclass"}


SELF_TVAR_NAME: Final = "_DT"
_TRANSFORM_SPEC_FOR_DATACLASSES = DataclassTransformSpec(
    eq_default=True,
    order_default=False,
    kw_only_default=False,
    frozen_default=False,
    field_specifiers=("dataclasses.Field", "dataclasses.field"),
)


class DataclassAttribute:
    def __init__(
        self,
        name: str,
        alias: str | None,
        is_in_init: bool,
        is_init_var: bool,
        has_default: bool,
        line: int,
        column: int,
        type: Type | None,
        info: TypeInfo,
        kw_only: bool,
    ) -> None:
        self.name = name
        self.alias = alias
        self.is_in_init = is_in_init
        self.is_init_var = is_init_var
        self.has_default = has_default
        self.line = line
        self.column = column
        self.type = type
        self.info = info
        self.kw_only = kw_only

    def to_argument(self, current_info: TypeInfo) -> Argument:
        arg_kind = ARG_POS
        if self.kw_only and self.has_default:
            arg_kind = ARG_NAMED_OPT
        elif self.kw_only and not self.has_default:
            arg_kind = ARG_NAMED
        elif not self.kw_only and self.has_default:
            arg_kind = ARG_OPT
        return Argument(
            variable=self.to_var(current_info),
            type_annotation=self.expand_type(current_info),
            initializer=None,
            kind=arg_kind,
        )

    def expand_type(self, current_info: TypeInfo) -> Optional[Type]:
        if self.type is not None and self.info.self_type is not None:
            # In general, it is not safe to call `expand_type()` during semantic analyzis,
            # however this plugin is called very late, so all types should be fully ready.
            # Also, it is tricky to avoid eager expansion of Self types here (e.g. because
            # we serialize attributes).
            return expand_type(self.type, {self.info.self_type.id: fill_typevars(current_info)})
        return self.type

    def to_var(self, current_info: TypeInfo) -> Var:
        return Var(self.alias or self.name, self.expand_type(current_info))

    def serialize(self) -> JsonDict:
        assert self.type
        return {
            "name": self.name,
            "alias": self.alias,
            "is_in_init": self.is_in_init,
            "is_init_var": self.is_init_var,
            "has_default": self.has_default,
            "line": self.line,
            "column": self.column,
            "type": self.type.serialize(),
            "kw_only": self.kw_only,
        }

    @classmethod
    def deserialize(
        cls, info: TypeInfo, data: JsonDict, api: SemanticAnalyzerPluginInterface
    ) -> DataclassAttribute:
        data = data.copy()
        if data.get("kw_only") is None:
            data["kw_only"] = False
        typ = deserialize_and_fixup_type(data.pop("type"), api)
        return cls(type=typ, info=info, **data)

    def expand_typevar_from_subtype(self, sub_type: TypeInfo) -> None:
        """Expands type vars in the context of a subtype when an attribute is inherited
        from a generic super type."""
        if self.type is not None:
            self.type = map_type_from_supertype(self.type, sub_type, self.info)


class DataclassTransformer:
    """Implement the behavior of @dataclass.

    Note that this may be executed multiple times on the same class, so
    everything here must be idempotent.

    This runs after the main semantic analysis pass, so you can assume that
    there are no placeholders.
    """

    def __init__(
        self,
        cls: ClassDef,
        # Statement must also be accepted since class definition itself may be passed as the reason
        # for subclass/metaclass-based uses of `typing.dataclass_transform`
        reason: Expression | Statement,
        spec: DataclassTransformSpec,
        api: SemanticAnalyzerPluginInterface,
    ) -> None:
        self._cls = cls
        self._reason = reason
        self._spec = spec
        self._api = api

    def transform(self) -> bool:
        """Apply all the necessary transformations to the underlying
        dataclass so as to ensure it is fully type checked according
        to the rules in PEP 557.
        """
        info = self._cls.info
        attributes = self.collect_attributes()
        if attributes is None:
            # Some definitions are not ready. We need another pass.
            return False
        for attr in attributes:
            if attr.type is None:
                return False
        decorator_arguments = {
            "init": self._get_bool_arg("init", True),
            "eq": self._get_bool_arg("eq", self._spec.eq_default),
            "order": self._get_bool_arg("order", self._spec.order_default),
            "frozen": self._get_bool_arg("frozen", self._spec.frozen_default),
            "slots": self._get_bool_arg("slots", False),
            "match_args": self._get_bool_arg("match_args", True),
        }
        py_version = self._api.options.python_version

        # If there are no attributes, it may be that the semantic analyzer has not
        # processed them yet. In order to work around this, we can simply skip generating
        # __init__ if there are no attributes, because if the user truly did not define any,
        # then the object default __init__ with an empty signature will be present anyway.
        if (
            decorator_arguments["init"]
            and ("__init__" not in info.names or info.names["__init__"].plugin_generated)
            and attributes
        ):

            with state.strict_optional_set(self._api.options.strict_optional):
                args = [
                    attr.to_argument(info)
                    for attr in attributes
                    if attr.is_in_init and not self._is_kw_only_type(attr.type)
                ]

            if info.fallback_to_any:
                # Make positional args optional since we don't know their order.
                # This will at least allow us to typecheck them if they are called
                # as kwargs
                for arg in args:
                    if arg.kind == ARG_POS:
                        arg.kind = ARG_OPT

                nameless_var = Var("")
                args = [
                    Argument(nameless_var, AnyType(TypeOfAny.explicit), None, ARG_STAR),
                    *args,
                    Argument(nameless_var, AnyType(TypeOfAny.explicit), None, ARG_STAR2),
                ]

            add_method_to_class(
                self._api, self._cls, "__init__", args=args, return_type=NoneType()
            )

        if (
            decorator_arguments["eq"]
            and info.get("__eq__") is None
            or decorator_arguments["order"]
        ):
            # Type variable for self types in generated methods.
            obj_type = self._api.named_type("builtins.object")
            self_tvar_expr = TypeVarExpr(
                SELF_TVAR_NAME, info.fullname + "." + SELF_TVAR_NAME, [], obj_type
            )
            info.names[SELF_TVAR_NAME] = SymbolTableNode(MDEF, self_tvar_expr)

        # Add <, >, <=, >=, but only if the class has an eq method.
        if decorator_arguments["order"]:
            if not decorator_arguments["eq"]:
                self._api.fail('"eq" must be True if "order" is True', self._reason)

            for method_name in ["__lt__", "__gt__", "__le__", "__ge__"]:
                # Like for __eq__ and __ne__, we want "other" to match
                # the self type.
                obj_type = self._api.named_type("builtins.object")
                order_tvar_def = TypeVarType(
                    SELF_TVAR_NAME, info.fullname + "." + SELF_TVAR_NAME, -1, [], obj_type
                )
                order_return_type = self._api.named_type("builtins.bool")
                order_args = [
                    Argument(Var("other", order_tvar_def), order_tvar_def, None, ARG_POS)
                ]

                existing_method = info.get(method_name)
                if existing_method is not None and not existing_method.plugin_generated:
                    assert existing_method.node
                    self._api.fail(
                        f'You may not have a custom "{method_name}" method when "order" is True',
                        existing_method.node,
                    )

                add_method_to_class(
                    self._api,
                    self._cls,
                    method_name,
                    args=order_args,
                    return_type=order_return_type,
                    self_type=order_tvar_def,
                    tvar_def=order_tvar_def,
                )

        parent_decorator_arguments = []
        for parent in info.mro[1:-1]:
            parent_args = parent.metadata.get("dataclass")
            if parent_args:
                parent_decorator_arguments.append(parent_args)

        if decorator_arguments["frozen"]:
            if any(not parent["frozen"] for parent in parent_decorator_arguments):
                self._api.fail("Cannot inherit frozen dataclass from a non-frozen one", info)
            self._propertize_callables(attributes, settable=False)
            self._freeze(attributes)
        else:
            if any(parent["frozen"] for parent in parent_decorator_arguments):
                self._api.fail("Cannot inherit non-frozen dataclass from a frozen one", info)
            self._propertize_callables(attributes)

        if decorator_arguments["slots"]:
            self.add_slots(info, attributes, correct_version=py_version >= (3, 10))

        self.reset_init_only_vars(info, attributes)

        if (
            decorator_arguments["match_args"]
            and (
                "__match_args__" not in info.names or info.names["__match_args__"].plugin_generated
            )
            and attributes
            and py_version >= (3, 10)
        ):
            str_type = self._api.named_type("builtins.str")
            literals: list[Type] = [
                LiteralType(attr.name, str_type) for attr in attributes if attr.is_in_init
            ]
            match_args_type = TupleType(literals, self._api.named_type("builtins.tuple"))
            add_attribute_to_class(self._api, self._cls, "__match_args__", match_args_type)

        self._add_dataclass_fields_magic_attribute()

        info.metadata["dataclass"] = {
            "attributes": [attr.serialize() for attr in attributes],
            "frozen": decorator_arguments["frozen"],
        }

        return True

    def add_slots(
        self, info: TypeInfo, attributes: list[DataclassAttribute], *, correct_version: bool
    ) -> None:
        if not correct_version:
            # This means that version is lower than `3.10`,
            # it is just a non-existent argument for `dataclass` function.
            self._api.fail(
                'Keyword argument "slots" for "dataclass" '
                "is only valid in Python 3.10 and higher",
                self._reason,
            )
            return

        generated_slots = {attr.name for attr in attributes}
        if (info.slots is not None and info.slots != generated_slots) or info.names.get(
            "__slots__"
        ):
            # This means we have a slots conflict.
            # Class explicitly specifies a different `__slots__` field.
            # And `@dataclass(slots=True)` is used.
            # In runtime this raises a type error.
            self._api.fail(
                '"{}" both defines "__slots__" and is used with "slots=True"'.format(
                    self._cls.name
                ),
                self._cls,
            )
            return

        info.slots = generated_slots

    def reset_init_only_vars(self, info: TypeInfo, attributes: list[DataclassAttribute]) -> None:
        """Remove init-only vars from the class and reset init var declarations."""
        for attr in attributes:
            if attr.is_init_var:
                if attr.name in info.names:
                    del info.names[attr.name]
                else:
                    # Nodes of superclass InitVars not used in __init__ cannot be reached.
                    assert attr.is_init_var
                for stmt in info.defn.defs.body:
                    if isinstance(stmt, AssignmentStmt) and stmt.unanalyzed_type:
                        lvalue = stmt.lvalues[0]
                        if isinstance(lvalue, NameExpr) and lvalue.name == attr.name:
                            # Reset node so that another semantic analysis pass will
                            # recreate a symbol node for this attribute.
                            lvalue.node = None

    def collect_attributes(self) -> list[DataclassAttribute] | None:
        """Collect all attributes declared in the dataclass and its parents.

        All assignments of the form

          a: SomeType
          b: SomeOtherType = ...

        are collected.

        Return None if some dataclass base class hasn't been processed
        yet and thus we'll need to ask for another pass.
        """
        cls = self._cls

        # First, collect attributes belonging to any class in the MRO, ignoring duplicates.
        #
        # We iterate through the MRO in reverse because attrs defined in the parent must appear
        # earlier in the attributes list than attrs defined in the child. See:
        # https://docs.python.org/3/library/dataclasses.html#inheritance
        #
        # However, we also want attributes defined in the subtype to override ones defined
        # in the parent. We can implement this via a dict without disrupting the attr order
        # because dicts preserve insertion order in Python 3.7+.
        found_attrs: dict[str, DataclassAttribute] = {}
        found_dataclass_supertype = False
        for info in reversed(cls.info.mro[1:-1]):
            if "dataclass_tag" in info.metadata and "dataclass" not in info.metadata:
                # We haven't processed the base class yet. Need another pass.
                return None
            if "dataclass" not in info.metadata:
                continue

            # Each class depends on the set of attributes in its dataclass ancestors.
            self._api.add_plugin_dependency(make_wildcard_trigger(info.fullname))
            found_dataclass_supertype = True

            for data in info.metadata["dataclass"]["attributes"]:
                name: str = data["name"]

                attr = DataclassAttribute.deserialize(info, data, self._api)
                # TODO: We shouldn't be performing type operations during the main
                #       semantic analysis pass, since some TypeInfo attributes might
                #       still be in flux. This should be performed in a later phase.
                with state.strict_optional_set(self._api.options.strict_optional):
                    attr.expand_typevar_from_subtype(cls.info)
                found_attrs[name] = attr

                sym_node = cls.info.names.get(name)
                if sym_node and sym_node.node and not isinstance(sym_node.node, Var):
                    self._api.fail(
                        "Dataclass attribute may only be overridden by another attribute",
                        sym_node.node,
                    )

        # Second, collect attributes belonging to the current class.
        current_attr_names: set[str] = set()
        kw_only = self._get_bool_arg("kw_only", self._spec.kw_only_default)
        for stmt in cls.defs.body:
            # Any assignment that doesn't use the new type declaration
            # syntax can be ignored out of hand.
            if not (isinstance(stmt, AssignmentStmt) and stmt.new_syntax):
                continue

            # a: int, b: str = 1, 'foo' is not supported syntax so we
            # don't have to worry about it.
            lhs = stmt.lvalues[0]
            if not isinstance(lhs, NameExpr):
                continue

            sym = cls.info.names.get(lhs.name)
            if sym is None:
                # There was probably a semantic analysis error.
                continue

            node = sym.node
            assert not isinstance(node, PlaceholderNode)

            if isinstance(node, TypeAlias):
                self._api.fail(
                    ("Type aliases inside dataclass definitions are not supported at runtime"),
                    node,
                )
                # Skip processing this node. This doesn't match the runtime behaviour,
                # but the only alternative would be to modify the SymbolTable,
                # and it's a little hairy to do that in a plugin.
                continue

            assert isinstance(node, Var)

            # x: ClassVar[int] is ignored by dataclasses.
            if node.is_classvar:
                continue

            # x: InitVar[int] is turned into x: int and is removed from the class.
            is_init_var = False
            node_type = get_proper_type(node.type)
            if (
                isinstance(node_type, Instance)
                and node_type.type.fullname == "dataclasses.InitVar"
            ):
                is_init_var = True
                node.type = node_type.args[0]

            if self._is_kw_only_type(node_type):
                kw_only = True

            has_field_call, field_args = self._collect_field_args(stmt.rvalue)

            is_in_init_param = field_args.get("init")
            if is_in_init_param is None:
                is_in_init = True
            else:
                is_in_init = bool(self._api.parse_bool(is_in_init_param))

            has_default = False
            # Ensure that something like x: int = field() is rejected
            # after an attribute with a default.
            if has_field_call:
                has_default = (
                    "default" in field_args
                    or "default_factory" in field_args
                    # alias for default_factory defined in PEP 681
                    or "factory" in field_args
                )

            # All other assignments are already type checked.
            elif not isinstance(stmt.rvalue, TempNode):
                has_default = True

            if not has_default:
                # Make all non-default attributes implicit because they are de-facto set
                # on self in the generated __init__(), not in the class body.
                sym.implicit = True

            is_kw_only = kw_only
            # Use the kw_only field arg if it is provided. Otherwise use the
            # kw_only value from the decorator parameter.
            field_kw_only_param = field_args.get("kw_only")
            if field_kw_only_param is not None:
                value = self._api.parse_bool(field_kw_only_param)
                if value is not None:
                    is_kw_only = value
                else:
                    self._api.fail('"kw_only" argument must be True or False.', stmt.rvalue)

            if sym.type is None and node.is_final and node.is_inferred:
                # This is a special case, assignment like x: Final = 42 is classified
                # annotated above, but mypy strips the `Final` turning it into x = 42.
                # We do not support inferred types in dataclasses, so we can try inferring
                # type for simple literals, and otherwise require an explicit type
                # argument for Final[...].
                typ = self._api.analyze_simple_literal_type(stmt.rvalue, is_final=True)
                if typ:
                    node.type = typ
                else:
                    self._api.fail(
                        "Need type argument for Final[...] with non-literal default in dataclass",
                        stmt,
                    )
                    node.type = AnyType(TypeOfAny.from_error)

            alias = None
            if "alias" in field_args:
                alias = self._api.parse_str_literal(field_args["alias"])
                if alias is None:
                    self._api.fail(
                        message_registry.DATACLASS_FIELD_ALIAS_MUST_BE_LITERAL,
                        stmt.rvalue,
                        code=errorcodes.LITERAL_REQ,
                    )

            current_attr_names.add(lhs.name)
            found_attrs[lhs.name] = DataclassAttribute(
                name=lhs.name,
                alias=alias,
                is_in_init=is_in_init,
                is_init_var=is_init_var,
                has_default=has_default,
                line=stmt.line,
                column=stmt.column,
                type=sym.type,
                info=cls.info,
                kw_only=is_kw_only,
            )

        all_attrs = list(found_attrs.values())
        if found_dataclass_supertype:
            all_attrs.sort(key=lambda a: a.kw_only)

        # Third, ensure that arguments without a default don't follow
        # arguments that have a default and that the KW_ONLY sentinel
        # is only provided once.
        found_default = False
        found_kw_sentinel = False
        for attr in all_attrs:
            # If we find any attribute that is_in_init, not kw_only, and that
            # doesn't have a default after one that does have one,
            # then that's an error.
            if found_default and attr.is_in_init and not attr.has_default and not attr.kw_only:
                # If the issue comes from merging different classes, report it
                # at the class definition point.
                context: Context = cls
                if attr.name in current_attr_names:
                    context = Context(line=attr.line, column=attr.column)
                self._api.fail(
                    "Attributes without a default cannot follow attributes with one", context
                )

            found_default = found_default or (attr.has_default and attr.is_in_init)
            if found_kw_sentinel and self._is_kw_only_type(attr.type):
                context = cls
                if attr.name in current_attr_names:
                    context = Context(line=attr.line, column=attr.column)
                self._api.fail(
                    "There may not be more than one field with the KW_ONLY type", context
                )
            found_kw_sentinel = found_kw_sentinel or self._is_kw_only_type(attr.type)
        return all_attrs

    def _freeze(self, attributes: list[DataclassAttribute]) -> None:
        """Converts all attributes to @property methods in order to
        emulate frozen classes.
        """
        info = self._cls.info
        for attr in attributes:
            sym_node = info.names.get(attr.name)
            if sym_node is not None:
                var = sym_node.node
                if isinstance(var, Var):
                    var.is_property = True
            else:
                var = attr.to_var(info)
                var.info = info
                var.is_property = True
                var._fullname = info.fullname + "." + var.name
                info.names[var.name] = SymbolTableNode(MDEF, var)

    def _propertize_callables(
        self, attributes: list[DataclassAttribute], settable: bool = True
    ) -> None:
        """Converts all attributes with callable types to @property methods.

        This avoids the typechecker getting confused and thinking that
        `my_dataclass_instance.callable_attr(foo)` is going to receive a
        `self` argument (it is not).

        """
        info = self._cls.info
        for attr in attributes:
            if isinstance(get_proper_type(attr.type), CallableType):
                var = attr.to_var(info)
                var.info = info
                var.is_property = True
                var.is_settable_property = settable
                var._fullname = info.fullname + "." + var.name
                info.names[var.name] = SymbolTableNode(MDEF, var)

    def _is_kw_only_type(self, node: Type | None) -> bool:
        """Checks if the type of the node is the KW_ONLY sentinel value."""
        if node is None:
            return False
        node_type = get_proper_type(node)
        if not isinstance(node_type, Instance):
            return False
        return node_type.type.fullname == "dataclasses.KW_ONLY"

    def _add_dataclass_fields_magic_attribute(self) -> None:
        # Only add if the class is a dataclasses dataclass, and omit it for dataclass_transform
        # classes.
        # It would be nice if this condition were reified rather than using an `is` check.
        # Only add if the class is a dataclasses dataclass, and omit it for dataclass_transform
        # classes.
        if self._spec is not _TRANSFORM_SPEC_FOR_DATACLASSES:
            return

        attr_name = "__dataclass_fields__"
        any_type = AnyType(TypeOfAny.explicit)
        field_type = self._api.named_type_or_none("dataclasses.Field", [any_type]) or any_type
        attr_type = self._api.named_type(
            "builtins.dict", [self._api.named_type("builtins.str"), field_type]
        )
        var = Var(name=attr_name, type=attr_type)
        var.info = self._cls.info
        var._fullname = self._cls.info.fullname + "." + attr_name
        var.is_classvar = True
        self._cls.info.names[attr_name] = SymbolTableNode(
            kind=MDEF, node=var, plugin_generated=True
        )

    def _collect_field_args(self, expr: Expression) -> tuple[bool, dict[str, Expression]]:
        """Returns a tuple where the first value represents whether or not
        the expression is a call to dataclass.field and the second is a
        dictionary of the keyword arguments that field() was called with.
        """
        if (
            isinstance(expr, CallExpr)
            and isinstance(expr.callee, RefExpr)
            and expr.callee.fullname in self._spec.field_specifiers
        ):
            # field() only takes keyword arguments.
            args = {}
            for name, arg, kind in zip(expr.arg_names, expr.args, expr.arg_kinds):
                if not kind.is_named():
                    if kind.is_named(star=True):
                        # This means that `field` is used with `**` unpacking,
                        # the best we can do for now is not to fail.
                        # TODO: we can infer what's inside `**` and try to collect it.
                        message = 'Unpacking **kwargs in "field()" is not supported'
                    else:
                        message = '"field()" does not accept positional arguments'
                    self._api.fail(message, expr)
                    return True, {}
                assert name is not None
                args[name] = arg
            return True, args
        return False, {}

    def _get_bool_arg(self, name: str, default: bool) -> bool:
        # Expressions are always CallExprs (either directly or via a wrapper like Decorator), so
        # we can use the helpers from common
        if isinstance(self._reason, Expression):
            return _get_decorator_bool_argument(
                ClassDefContext(self._cls, self._reason, self._api), name, default
            )

        # Subclass/metaclass use of `typing.dataclass_transform` reads the parameters from the
        # class's keyword arguments (ie `class Subclass(Parent, kwarg1=..., kwarg2=...)`)
        expression = self._cls.keywords.get(name)
        if expression is not None:
            value = self._api.parse_bool(self._cls.keywords[name])
            if value is not None:
                return value
            else:
                self._api.fail(f'"{name}" argument must be True or False', expression)
        return default


def add_dataclass_tag(info: TypeInfo) -> None:
    # The value is ignored, only the existence matters.
    info.metadata["dataclass_tag"] = {}


def dataclass_tag_callback(ctx: ClassDefContext) -> None:
    """Record that we have a dataclass in the main semantic analysis pass.

    The later pass implemented by DataclassTransformer will use this
    to detect dataclasses in base classes.
    """
    add_dataclass_tag(ctx.cls.info)


def dataclass_class_maker_callback(ctx: ClassDefContext) -> bool:
    """Hooks into the class typechecking process to add support for dataclasses."""
    transformer = DataclassTransformer(
        ctx.cls, ctx.reason, _get_transform_spec(ctx.reason), ctx.api
    )
    return transformer.transform()


def _get_transform_spec(reason: Expression) -> DataclassTransformSpec:
    """Find the relevant transform parameters from the decorator/parent class/metaclass that
    triggered the dataclasses plugin.

    Although the resulting DataclassTransformSpec is based on the typing.dataclass_transform
    function, we also use it for traditional dataclasses.dataclass classes as well for simplicity.
    In those cases, we return a default spec rather than one based on a call to
    `typing.dataclass_transform`.
    """
    if _is_dataclasses_decorator(reason):
        return _TRANSFORM_SPEC_FOR_DATACLASSES

    spec = find_dataclass_transform_spec(reason)
    assert spec is not None, (
        "trying to find dataclass transform spec, but reason is neither dataclasses.dataclass nor "
        "decorated with typing.dataclass_transform"
    )
    return spec


def _is_dataclasses_decorator(node: Node) -> bool:
    if isinstance(node, CallExpr):
        node = node.callee
    if isinstance(node, RefExpr):
        return node.fullname in dataclass_makers
    return False
