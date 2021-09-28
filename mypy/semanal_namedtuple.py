"""Semantic analysis of named tuple definitions.

This is conceptually part of mypy.semanal.
"""
from copy import copy
from contextlib import contextmanager
from keyword import iskeyword
from typing import Tuple, List, Dict, Mapping, Optional, cast, Iterator
from typing_extensions import Final

from mypy import errorcodes as codes
from mypy.types import (
    Type, TupleType, AnyType, TypeOfAny, CallableType, TypeType, TypeVarType,
    UnboundType
)
from mypy.semanal_shared import (
    SemanticAnalyzerInterface, set_callable_name, calculate_tuple_fallback, PRIORITY_FALLBACKS
)
from mypy.nodes import (
    Var, EllipsisExpr, Argument, StrExpr, ExpressionStmt, NameExpr,
    AssignmentStmt, PassStmt, Decorator, FuncBase, ClassDef, Expression, RefExpr, TypeInfo,
    NamedTupleExpr, CallExpr, Context, TupleExpr, ListExpr, SymbolTableNode, FuncDef, Block,
    TempNode, SymbolTable, TypeVarExpr,
    ArgKind, ARG_POS, ARG_NAMED_OPT, ARG_OPT, MDEF
)
from mypy.options import Options
from mypy.exprtotype import expr_to_unanalyzed_type, TypeTranslationError
from mypy.util import get_unique_redefinition_name

# Matches "_prohibited" in typing.py, but adds __annotations__, which works at runtime but can't
# easily be supported in a static checker.
NAMEDTUPLE_PROHIBITED_NAMES: Final = (
    "__new__",
    "__init__",
    "__slots__",
    "__getnewargs__",
    "_fields",
    "_field_defaults",
    "_field_types",
    "_make",
    "_replace",
    "_asdict",
    "_source",
    "__annotations__",
)

NAMEDTUP_CLASS_ERROR: Final = (
    "Invalid statement in NamedTuple definition; " 'expected "field_name: field_type [= default]"'
)

SELF_TVAR_NAME: Final = "_NT"

# Type alias for inner structure of NamedTuple type.
NamedTupleStructure = Optional[Tuple[
    List[str],
    List[Type],
    List[Expression],
    str,
    bool,
]]


class NamedTupleAnalyzer:
    def __init__(self, options: Options, api: SemanticAnalyzerInterface) -> None:
        self.options = options
        self.api = api

    def analyze_namedtuple_classdef(self, defn: ClassDef, is_stub_file: bool
                                    ) -> Tuple[bool, Optional[TypeInfo]]:
        """Analyze if given class definition can be a named tuple definition.

        Return a tuple where first item indicates whether this can possibly be a named tuple,
        and the second item is the corresponding TypeInfo (may be None if not ready and should be
        deferred).
        """
        for base_expr in defn.base_type_exprs:
            if isinstance(base_expr, RefExpr):
                self.api.accept(base_expr)
                if base_expr.fullname == 'typing.NamedTuple':
                    result = self.check_namedtuple_classdef(defn, is_stub_file)
                    if result is None:
                        # This is a valid named tuple, but some types are incomplete.
                        return True, None
                    items, types, default_items = result
                    info = self.build_namedtuple_typeinfo(
                        defn.name, items, types, default_items, defn.line)
                    defn.info = info
                    defn.analyzed = NamedTupleExpr(info, is_typed=True)
                    defn.analyzed.line = defn.line
                    defn.analyzed.column = defn.column
                    # All done: this is a valid named tuple with all types known.
                    return True, info
        # This can't be a valid named tuple.
        return False, None

    def check_namedtuple_classdef(self, defn: ClassDef, is_stub_file: bool
                                  ) -> Optional[Tuple[List[str],
                                                List[Type],
                                                Dict[str, Expression]]]:
        """Parse and validate fields in named tuple class definition.

        Return a three tuple:
          * field names
          * field types
          * field default values
        or None, if any of the types are not ready.
        """
        if self.options.python_version < (3, 6) and not is_stub_file:
            self.fail('NamedTuple class syntax is only supported in Python 3.6', defn)
            return [], [], {}
        if len(defn.base_type_exprs) > 1:
            self.fail('NamedTuple should be a single base', defn)
        items: List[str] = []
        types: List[Type] = []
        default_items: Dict[str, Expression] = {}
        for stmt in defn.defs.body:
            if not isinstance(stmt, AssignmentStmt):
                # Still allow pass or ... (for empty namedtuples).
                if (isinstance(stmt, PassStmt) or
                    (isinstance(stmt, ExpressionStmt) and
                        isinstance(stmt.expr, EllipsisExpr))):
                    continue
                # Also allow methods, including decorated ones.
                if isinstance(stmt, (Decorator, FuncBase)):
                    continue
                # And docstrings.
                if (isinstance(stmt, ExpressionStmt) and
                        isinstance(stmt.expr, StrExpr)):
                    continue
                self.fail(NAMEDTUP_CLASS_ERROR, stmt)
            elif len(stmt.lvalues) > 1 or not isinstance(stmt.lvalues[0], NameExpr):
                # An assignment, but an invalid one.
                self.fail(NAMEDTUP_CLASS_ERROR, stmt)
            else:
                # Append name and type in this case...
                name = stmt.lvalues[0].name
                items.append(name)
                if stmt.type is None:
                    types.append(AnyType(TypeOfAny.unannotated))
                else:
                    analyzed = self.api.anal_type(stmt.type)
                    if analyzed is None:
                        # Something is incomplete. We need to defer this named tuple.
                        return None
                    types.append(analyzed)
                # ...despite possible minor failures that allow further analyzis.
                if name.startswith('_'):
                    self.fail('NamedTuple field name cannot start with an underscore: {}'
                              .format(name), stmt)
                if stmt.type is None or hasattr(stmt, 'new_syntax') and not stmt.new_syntax:
                    self.fail(NAMEDTUP_CLASS_ERROR, stmt)
                elif isinstance(stmt.rvalue, TempNode):
                    # x: int assigns rvalue to TempNode(AnyType())
                    if default_items:
                        self.fail('Non-default NamedTuple fields cannot follow default fields',
                                  stmt)
                else:
                    default_items[name] = stmt.rvalue
        return items, types, default_items

    def check_namedtuple(self,
                         node: Expression,
                         var_name: Optional[str],
                         is_func_scope: bool) -> Tuple[Optional[str], Optional[TypeInfo]]:
        """Check if a call defines a namedtuple.

        The optional var_name argument is the name of the variable to
        which this is assigned, if any.

        Return a tuple of two items:
          * Internal name of the named tuple (e.g. the name passed as an argument to namedtuple)
            or None if it is not a valid named tuple
          * Corresponding TypeInfo, or None if not ready.

        If the definition is invalid but looks like a namedtuple,
        report errors but return (some) TypeInfo.
        """
        if not isinstance(node, CallExpr):
            return None, None
        call = node
        callee = call.callee
        if not isinstance(callee, RefExpr):
            return None, None
        fullname = callee.fullname
        if fullname == 'collections.namedtuple':
            is_typed = False
        elif fullname == 'typing.NamedTuple':
            is_typed = True
        else:
            return None, None

        result = self.parse_namedtuple_args(call, fullname, var_name)
        if result is None:
            # Error. Construct dummy return value.
            if var_name:
                name = var_name
            else:
                name = 'namedtuple@' + str(call.line)
            info = self.build_namedtuple_typeinfo(name, [], [], {}, node.line)
            self.store_namedtuple_info(info, name, call, is_typed)
            return name, info

        items, types, defaults, typename, ok = result
        if not ok:
            # This is a valid named tuple but some types are not ready.
            return typename, None

        # We use the variable name as the class name if it exists. If
        # it doesn't, we use the name passed as an argument. We prefer
        # the variable name because it should be unique inside a
        # module, and so we don't need to disambiguate it with a line
        # number.
        if var_name:
            name = var_name
        else:
            name = typename

        if var_name is None or is_func_scope:
            # There are two special cases where need to give it a unique name derived
            # from the line number:
            #   * This is a base class expression, since it often matches the class name:
            #         class NT(NamedTuple('NT', [...])):
            #             ...
            #   * This is a local (function or method level) named tuple, since
            #     two methods of a class can define a named tuple with the same name,
            #     and they will be stored in the same namespace (see below).
            name += '@' + str(call.line)
        if len(defaults) > 0:
            default_items = {
                arg_name: default
                for arg_name, default in zip(items[-len(defaults):], defaults)
            }
        else:
            default_items = {}
        info = self.build_namedtuple_typeinfo(name, items, types, default_items, node.line)
        # If var_name is not None (i.e. this is not a base class expression), we always
        # store the generated TypeInfo under var_name in the current scope, so that
        # other definitions can use it.
        if var_name:
            self.store_namedtuple_info(info, var_name, call, is_typed)
        # There are three cases where we need to store the generated TypeInfo
        # second time (for the purpose of serialization):
        #   * If there is a name mismatch like One = NamedTuple('Other', [...])
        #     we also store the info under name 'Other@lineno', this is needed
        #     because classes are (de)serialized using their actual fullname, not
        #     the name of l.h.s.
        #   * If this is a method level named tuple. It can leak from the method
        #     via assignment to self attribute and therefore needs to be serialized
        #     (local namespaces are not serialized).
        #   * If it is a base class expression. It was not stored above, since
        #     there is no var_name (but it still needs to be serialized
        #     since it is in MRO of some class).
        if name != var_name or is_func_scope:
            # NOTE: we skip local namespaces since they are not serialized.
            self.api.add_symbol_skip_local(name, info)
        return typename, info

    def store_namedtuple_info(self, info: TypeInfo, name: str,
                              call: CallExpr, is_typed: bool) -> None:
        self.api.add_symbol(name, info, call)

        # We need a copy of `CallExpr` node without `analyzed` type
        # to show better error messages of invalid namedtuple calls.
        # Without this hack we would need to create errors manually in semanal.
        # Which is hard and inconsistent with how other errors are shown.
        # But, with this hack we just inspect the call with typechecker:
        # this way we can be 100% sure everything is correct.
        call_copy = copy(call)
        call.analyzed = NamedTupleExpr(info, call=call_copy, is_typed=is_typed)
        call.analyzed.set_line(call.line, call.column)

    def parse_namedtuple_args(self, call: CallExpr,
                              fullname: str, var_name: Optional[str]) -> NamedTupleStructure:
        """Parse a namedtuple() call into data needed to construct a type."""
        call_analyzer = NamedTupleCallAnalyzer(self.options, self.api, call, fullname, var_name)
        return call_analyzer.parse_structure()

    def build_namedtuple_typeinfo(self,
                                  name: str,
                                  items: List[str],
                                  types: List[Type],
                                  default_items: Mapping[str, Expression],
                                  line: int) -> TypeInfo:
        strtype = self.api.named_type('builtins.str')
        implicit_any = AnyType(TypeOfAny.special_form)
        basetuple_type = self.api.named_type('builtins.tuple', [implicit_any])
        dictype = (self.api.named_type_or_none('builtins.dict', [strtype, implicit_any])
                   or self.api.named_type('builtins.object'))
        # Actual signature should return OrderedDict[str, Union[types]]
        ordereddictype = (self.api.named_type_or_none('builtins.dict', [strtype, implicit_any])
                          or self.api.named_type('builtins.object'))
        fallback = self.api.named_type('builtins.tuple', [implicit_any])
        # Note: actual signature should accept an invariant version of Iterable[UnionType[types]].
        # but it can't be expressed. 'new' and 'len' should be callable types.
        iterable_type = self.api.named_type_or_none('typing.Iterable', [implicit_any])
        function_type = self.api.named_type('builtins.function')

        info = self.api.basic_new_typeinfo(name, fallback, line)
        info.is_named_tuple = True
        tuple_base = TupleType(types, fallback)
        info.tuple_type = tuple_base
        info.line = line
        # For use by mypyc.
        info.metadata['namedtuple'] = {'fields': items.copy()}

        # We can't calculate the complete fallback type until after semantic
        # analysis, since otherwise base classes might be incomplete. Postpone a
        # callback function that patches the fallback.
        self.api.schedule_patch(PRIORITY_FALLBACKS,
                                lambda: calculate_tuple_fallback(tuple_base))

        def add_field(var: Var, is_initialized_in_class: bool = False,
                      is_property: bool = False) -> None:
            var.info = info
            var.is_initialized_in_class = is_initialized_in_class
            var.is_property = is_property
            var._fullname = '%s.%s' % (info.fullname, var.name)
            info.names[var.name] = SymbolTableNode(MDEF, var)

        fields = [Var(item, typ) for item, typ in zip(items, types)]
        for var in fields:
            add_field(var, is_property=True)
        # We can't share Vars between fields and method arguments, since they
        # have different full names (the latter are normally used as local variables
        # in functions, so their full names are set to short names when generated methods
        # are analyzed).
        vars = [Var(item, typ) for item, typ in zip(items, types)]

        tuple_of_strings = TupleType([strtype for _ in items], basetuple_type)
        add_field(Var('_fields', tuple_of_strings), is_initialized_in_class=True)
        add_field(Var('_field_types', dictype), is_initialized_in_class=True)
        add_field(Var('_field_defaults', dictype), is_initialized_in_class=True)
        add_field(Var('_source', strtype), is_initialized_in_class=True)
        add_field(Var('__annotations__', ordereddictype), is_initialized_in_class=True)
        add_field(Var('__doc__', strtype), is_initialized_in_class=True)

        tvd = TypeVarType(SELF_TVAR_NAME, info.fullname + '.' + SELF_TVAR_NAME,
                         -1, [], info.tuple_type)
        selftype = tvd

        def add_method(funcname: str,
                       ret: Type,
                       args: List[Argument],
                       is_classmethod: bool = False,
                       is_new: bool = False,
                       ) -> None:
            if is_classmethod or is_new:
                first = [Argument(Var('_cls'), TypeType.make_normalized(selftype), None, ARG_POS)]
            else:
                first = [Argument(Var('_self'), selftype, None, ARG_POS)]
            args = first + args

            types = [arg.type_annotation for arg in args]
            items = [arg.variable.name for arg in args]
            arg_kinds = [arg.kind for arg in args]
            assert None not in types
            signature = CallableType(cast(List[Type], types), arg_kinds, items, ret,
                                     function_type)
            signature.variables = [tvd]
            func = FuncDef(funcname, args, Block([]))
            func.info = info
            func.is_class = is_classmethod
            func.type = set_callable_name(signature, func)
            func._fullname = info.fullname + '.' + funcname
            func.line = line
            if is_classmethod:
                v = Var(funcname, func.type)
                v.is_classmethod = True
                v.info = info
                v._fullname = func._fullname
                func.is_decorated = True
                dec = Decorator(func, [NameExpr('classmethod')], v)
                dec.line = line
                sym = SymbolTableNode(MDEF, dec)
            else:
                sym = SymbolTableNode(MDEF, func)
            sym.plugin_generated = True
            info.names[funcname] = sym

        add_method('_replace', ret=selftype,
                   args=[Argument(var, var.type, EllipsisExpr(), ARG_NAMED_OPT) for var in vars])

        def make_init_arg(var: Var) -> Argument:
            default = default_items.get(var.name, None)
            kind = ARG_POS if default is None else ARG_OPT
            return Argument(var, var.type, default, kind)

        add_method('__new__', ret=selftype,
                   args=[make_init_arg(var) for var in vars],
                   is_new=True)
        add_method('_asdict', args=[], ret=ordereddictype)
        special_form_any = AnyType(TypeOfAny.special_form)
        add_method('_make', ret=selftype, is_classmethod=True,
                   args=[Argument(Var('iterable', iterable_type), iterable_type, None, ARG_POS),
                         Argument(Var('new'), special_form_any, EllipsisExpr(), ARG_NAMED_OPT),
                         Argument(Var('len'), special_form_any, EllipsisExpr(), ARG_NAMED_OPT)])

        self_tvar_expr = TypeVarExpr(SELF_TVAR_NAME, info.fullname + '.' + SELF_TVAR_NAME,
                                     [], info.tuple_type)
        info.names[SELF_TVAR_NAME] = SymbolTableNode(MDEF, self_tvar_expr)
        return info

    @contextmanager
    def save_namedtuple_body(self, named_tuple_info: TypeInfo) -> Iterator[None]:
        """Preserve the generated body of class-based named tuple and then restore it.

        Temporarily clear the names dict so we don't get errors about duplicate names
        that were already set in build_namedtuple_typeinfo (we already added the tuple
        field names while generating the TypeInfo, and actual duplicates are
        already reported).
        """
        nt_names = named_tuple_info.names
        named_tuple_info.names = SymbolTable()

        yield

        # Make sure we didn't use illegal names, then reset the names in the typeinfo.
        for prohibited in NAMEDTUPLE_PROHIBITED_NAMES:
            if prohibited in named_tuple_info.names:
                if nt_names.get(prohibited) is named_tuple_info.names[prohibited]:
                    continue
                ctx = named_tuple_info.names[prohibited].node
                assert ctx is not None
                self.fail('Cannot overwrite NamedTuple attribute "{}"'.format(prohibited),
                          ctx)

        # Restore the names in the original symbol table. This ensures that the symbol
        # table contains the field objects created by build_namedtuple_typeinfo. Exclude
        # __doc__, which can legally be overwritten by the class.
        for key, value in nt_names.items():
            if key in named_tuple_info.names:
                if key == '__doc__':
                    continue
                sym = named_tuple_info.names[key]
                if isinstance(sym.node, (FuncBase, Decorator)) and not sym.plugin_generated:
                    # Keep user-defined methods as is.
                    continue
                # Keep existing (user-provided) definitions under mangled names, so they
                # get semantically analyzed.
                r_key = get_unique_redefinition_name(key, named_tuple_info.names)
                named_tuple_info.names[r_key] = sym
            named_tuple_info.names[key] = value

    # Helpers

    def fail(self, msg: str, ctx: Context) -> None:
        self.api.fail(msg, ctx)


class NamedTupleCallAnalyzer:
    """
    Analyzes ``namedtuple()`` and ``NamedTuple()`` calls.

    Our single public ``parse_structure`` method returns a 5-tuple:
    - List of argument names
    - List of argument types
    - List of default values
    - First argument of namedtuple
    - Whether all types are ready.

    Returns ``None`` if the definition didn't typecheck.
    """

    # TODO: test `NamedTuple('N')` without assignment: just as an expression

    def __init__(
        self,
        options: Options,
        api: SemanticAnalyzerInterface,
        call: CallExpr,
        fullname: str,
        var_name: Optional[str],
    ) -> None:
        self._options = options
        self._api = api
        self._call = call
        self._var_name = var_name
        self._fullname = fullname
        self._shortname = 'NamedTuple' if fullname == 'typing.NamedTuple' else 'namedtuple'

    @property
    def _args(self) -> List[Expression]:
        return self._call.args

    @property
    def _kinds(self) -> List[ArgKind]:
        return self._call.arg_kinds

    @property
    def _names(self) -> List[Optional[str]]:
        return self._call.arg_names

    def _fail(
        self,
        msg: str,
        context: Optional[Context] = None,
        code: Optional[codes.ErrorCode] = None,
    ) -> None:
        """Raises error in semantic analyzer.

        But, the most important question is: when do we raise errors?

        Let's start from when we **do not** raise errors:
        - When we got incorrect types / arguments names.
          We use typechecker to analyze the original call,
          so, we don't need to replicate its features.
          We would have this covered.
        - When we can recover from error, no need to raise false-positives.

        So, our main task here is to raise errors when non-literal values are used.
        It won't be covered by type-checker, but without literal values,
        we cannot construct a valid namedtuple.

        For example, both these cases are fine from typechecker's perspective:
        1. ``namedtuple('N', field_names=['a', 'b', 'c'], rename=False)``
        2. ``namedtuple('N', field_names=field_names_var, rename=rename)``

        We can analyze the first one, but we cannot analyze the second one.
        That's why we need to raises semanal errors there.
        """
        self._api.fail(msg, context or self._call, code=code)

    def parse_structure(self) -> NamedTupleStructure:
        if not self._args:
            return None  # We need at least a `typename`

        typename = self._parse_typename()
        if typename is None:
            return None  # Typename is invalid: not literal str or wrong kw-name

        if len(self._args) == 1:
            # Empty named tuple definition
            return self._validate_fields([], [], [], typename)

        if self._fullname == 'typing.NamedTuple':
            return self._parse_typing_namedtuple(typename)
        elif self._fullname == 'collections.namedtuple':
            return self._parse_collections_namedtuple(typename)
        # Should not happen:
        raise ValueError('Got unexpected type {}'.format(self._fullname))

    def _parse_typename(self) -> Optional[str]:
        typename_index = self._find_name_index('typename')

        arg: Optional[Expression] = None
        if typename_index is not None:  # Named argument
            if not self._kinds[typename_index].is_named():
                return None
            arg = self._args[typename_index]
        elif self._kinds[0].is_positional():  # Positional
            arg = self._args[0]
        if not isinstance(arg, StrExpr):
            self._fail(
                f'"{self._shortname}()" expects a string literal '
                'as the typename argument',
                arg,
            )
            return None
        return self._validate_typename(arg.value)

    def _parse_typing_namedtuple(self, typename: str) -> NamedTupleStructure:
        """Parsing ``typing.NamedTuple()`` call.

        In all of the examples below arguments can be named or positional.

        Possible valid cases:
        1. ``N = NamedTuple('N')`` - empty namedtuple
        2. ``N = NamedTuple('N', [('a', int)])``
        3. ``N = NamedTuple(typename='N', fields=(('a', int),))`` or ``fields=[]``
        4. ``N = NamedTuple('N', a=int)`` with kwargs

        Corner cases, but still valid:
        7. ``N = NamedTuple('N', ())``, - empty namedtuple,
           we also count ``[]`` here, ``fields`` can be named or positional
        6. ``N = NamedTuple('N', fields=None, a=int)``,
           in this case ``fields`` will not be present as a namedtuple field
        7. ``N = NamedTuple('N', None, a=int)``
        8. ``N = NamedTuple(a=int, typename='N')``
           kw-arguments can be in a different order, that's fine

        Everything else is considered **invalid**.
        We only accept statically known types.
        """
        fields_arg_index = self._find_name_index('fields')
        fields_is_named = fields_arg_index is not None

        if fields_arg_index is None and self._kinds[1].is_positional():
            fields_arg_index = 1  # Positional `fields` argument
        if fields_arg_index is None:
            return self._typing_namedtuple_from_kwargs(typename)

        assert isinstance(fields_arg_index, int)
        return self._typing_namedtuple_from_fields(
            typename, fields_arg_index, is_named=fields_is_named,
        )

    def _typing_namedtuple_from_fields(
        self, typename: str, fields_arg_index: int, *, is_named: bool,
    ) -> NamedTupleStructure:
        fields_arg = self._args[fields_arg_index]

        if (
            isinstance(fields_arg, NameExpr)
            and fields_arg.name == 'None'
            and (is_named or self._kinds[fields_arg_index].is_positional())
        ):
            # Named `fields` argument still can be `None`, that's fine.
            # This can happen in a case like `NamedTuple('N', fields=None, a=int)`
            # We need to try the kwargs.
            return self._typing_namedtuple_from_kwargs(typename)

        if not isinstance(fields_arg, (TupleExpr, ListExpr)):
            self._fail(
                'List or tuple literal expected as the fields argument'
                f'to "{self._shortname}()"',
                fields_arg,
            )
            return None
        if self._args[2:]:
            # We only can have `fields` or `kwargs`.
            # `fields` was provided, we expect no more arguments.
            return None

        names = []
        types = []
        for item in fields_arg.items:
            if not isinstance(item, TupleExpr) or len(item.items) != 2:
                self._fail(f'Invalid "{self._shortname}" field definition', item)
                return None

            name, type_node = item.items
            if not isinstance(name, StrExpr):
                self._fail(f'Invalid "{self._shortname}" field name', item)
                return None

            names.append(name.value)
            field_type = self._analyze_type(type_node)
            if field_type is None:
                return [], [], [], typename, False  # Type is not ready, defer.
            types.append(field_type)
        return self._validate_fields(names, types, [], typename)

    def _typing_namedtuple_from_kwargs(self, typename: str) -> NamedTupleStructure:
        names: List[str] = []
        types = []
        for index, (name, kind) in enumerate(zip(self._names, self._kinds)):
            if kind.is_named() and name in ('fields', 'typename'):
                # We can have named `fields` or `typename` argument in
                # `NamedTuple(..., typename='N', ..., fields=None, ...)`
                # It can happen at any position. We just ignore it.
                continue

            current_arg = self._args[index]

            if (
                index == 1
                and kind.is_positional()
                and isinstance(current_arg, NameExpr)
                and current_arg.name == 'None'
            ):
                # We can have positional `None` as in `NamedTuple('N', None, ...)`
                continue

            if not kind.is_named():
                if index > 1:
                    return None
                continue

            field_type = self._analyze_type(current_arg)
            if field_type is None:
                return [], [], [], typename, False  # Type is not ready, defer.

            name = self._names[index]
            assert isinstance(name, str)
            names.append(name)
            types.append(field_type)
        return self._validate_fields(names, types, [], typename)

    def _parse_collections_namedtuple(self, typename: str) -> NamedTupleStructure:
        """Parsing ``collections.namedtuple()`` call.

        In all of the examples below arguments can be named or positional.

        Possible valid cases:
        1. ``N = namedtuple('N')`` - empty named tuple
        2. ``N = namedtuple('N', 'a,b')`` - fields defined as a string
        3. ``N = namedtuple('N', ['a', 'b'])`` - tuple / list of str fields
        4. ``N = namedtuple(typename='N', field_names=['a'])``

        Corner cases, but still valid:
        5. ``N = namedtuple(field_names=['a'], typename='N')``
           kw-arguments can be in a different order, that's fine
        6. ``N = namedtuple('N', (), defaults=[], rename=True)``

        We also make use of optional kw-only
        ``defaults: None | list[Expression] | tuple[Expression, ...]``
        argument to tell which arguments
        are required and which one have defaults.

        We currently support, but do nothing
        for these kw-only arguments: ``rename=False, module=None``.
        """
        field_names_index = self._find_name_index('field_names')

        # There are two options:
        # 1. `field_names` is named: it can have any index in the call expr
        # 2. `field_names` is positional: only `1` index, after `typename`
        if field_names_index is None and self._kinds[1].is_positional():
            field_names_index = 1

        if field_names_index is None:
            return None

        field_names_arg = self._args[field_names_index]
        names: List[str] = []

        # `field_names` can be: comma-separated `str`, `list[str]`, or `tuple[str]`
        if isinstance(field_names_arg, (TupleExpr, ListExpr)):
            for item in field_names_arg.items:
                if not isinstance(item, StrExpr):
                    self._fail(
                        f'String literal expected as "{self._shortname}()" field',
                        item,
                    )
                    return None
                names.append(item.value)
        elif isinstance(field_names_arg, StrExpr):
            names = [
                field.strip()
                for field in field_names_arg.value.replace(',', ' ').split()
            ]
        else:
            self._fail(
                'String, list or tuple literal expected as the field_names argument'
                f'to "{self._shortname}()"',
                field_names_arg,
            )
            return None

        # Types are always `Any` for `collections.namedtuple`.
        types: List[Type] = [
            AnyType(TypeOfAny.implementation_artifact)
            for _ in range(len(names))
        ]

        # `defaults` is always a kw-only argument, it might be invalid though.
        # We only understand list and tuple expressions.
        defaults_index = self._find_name_index('defaults')
        if defaults_index is not None:
            defaults_arg = self._args[defaults_index]
            if not isinstance(defaults_arg, (TupleExpr, ListExpr)):
                self._fail(
                    'List or tuple literal expected as the defaults argument '
                    f'to "{self._shortname}()"',
                    defaults_arg,
                )
                return None
            defaults = list(defaults_arg.items)
        else:
            defaults = []

        # `rename` is always kw-only, it changes invalid field names if passed.
        # We only understand literal bool values.
        rename_index = self._find_name_index('rename')
        if rename_index is not None:
            rename_arg = self._args[rename_index]
            if not isinstance(rename_arg, NameExpr) or rename_arg.name not in ('True', 'False'):
                self._fail(
                    'Bool literal expected as the rename argument '
                    f'to "{self._shortname}()"',
                    rename_arg,
                )
                return None
            rename = rename_arg.name == 'True'
        else:
            rename = False

        return self._validate_fields(names, types, defaults, typename, rename=rename)

    def _validate_typename(self, typename: Optional[str]) -> Optional[str]:
        if self._var_name is not None and typename != self._var_name:
            self._fail('First argument to "{}()" should be "{}", not "{}"'.format(
                self._shortname, self._var_name, typename,
            ), self._call, code=codes.NAME_MATCH)
            # We don't stop at this error, maybe there are other ones?
            return typename
        return typename

    def _validate_fields(
        self,
        field_names: List[str], types: List[Type],
        defaults: List[Expression], typename: str, *,
        rename: bool = False,
    ) -> NamedTupleStructure:
        # We follow the same error order as in `collections.namedtuple()`,
        # we also use the same error messages.
        # The only difference is that we try to raise as many as possible,
        # instead of failing on the first encountered error.
        # We also don't type check argument types here.
        is_valid = True

        if rename:
            seen = set()
            for index, name in enumerate(field_names):
                if (
                    not name.isidentifier()
                    or iskeyword(name)
                    or name.startswith('_')
                    or name in seen
                ):
                    field_names[index] = f'_{index}'
                seen.add(name)

        for name in [typename] + field_names:
            if not name.isidentifier():
                self._fail('Type names and field names must be valid '
                           f'identifiers: {name!r}')
                is_valid = False
            if iskeyword(name):
                self._fail('Type names and field names cannot be a '
                           f'keyword: {name!r}')
                is_valid = False

        seen = set()
        for name in field_names:
            if name.startswith('_') and not rename:
                self._fail(f'Field names cannot start with an underscore: {name!r}')
                is_valid = False
            if name in seen:
                self._fail(f'Encountered duplicate field name: {name!r}')
                is_valid = False
            seen.add(name)

        if len(defaults) > len(field_names):
            self._fail('Got more default values than field names')
            is_valid = False

        if not is_valid:
            return None
        return field_names, types, defaults, typename, True

    def _find_name_index(self, name: str) -> Optional[int]:
        try:
            index = self._names.index(name)
        except ValueError:
            return None
        assert self._kinds[index].is_named()  # Sanity check
        return index

    def _analyze_type(self, type_node: Expression) -> Optional[Type]:
        try:
            typ = expr_to_unanalyzed_type(
                type_node, self._options, self._api.is_stub_file,
            )
        except TypeTranslationError:
            return None

        analyzed = self._api.anal_type(typ)
        # Workaround #4987 and avoid introducing a bogus UnboundType
        if isinstance(analyzed, UnboundType):
            analyzed = AnyType(TypeOfAny.from_error)
        # These should be all known,
        # otherwise we would defer in visit_assignment_stmt().
        return analyzed
