"""Plugin system for extending mypy."""

from collections import OrderedDict
from abc import abstractmethod
from typing import Callable, List, Tuple, Optional, NamedTuple, TypeVar, Set, \
    cast

from mypy import messages
from mypy.nodes import Expression, StrExpr, IntExpr, UnaryExpr, Context, \
    DictExpr, ClassDef, Argument, Var, TypeInfo, FuncDef, Block, \
    SymbolTableNode, MDEF, CallExpr, RefExpr, AssignmentStmt, TempNode, \
    ARG_POS, ARG_OPT, EllipsisExpr, NameExpr
from mypy.types import (
    Type, Instance, CallableType, TypedDictType, UnionType, NoneTyp, FunctionLike, TypeVarType,
    AnyType, TypeList, UnboundType, TypeOfAny
)
from mypy.messages import MessageBuilder
from mypy.options import Options


class TypeAnalyzerPluginInterface:
    """Interface for accessing semantic analyzer functionality in plugins."""

    @abstractmethod
    def fail(self, msg: str, ctx: Context) -> None:
        raise NotImplementedError

    @abstractmethod
    def named_type(self, name: str, args: List[Type]) -> Instance:
        raise NotImplementedError

    @abstractmethod
    def analyze_type(self, typ: Type) -> Type:
        raise NotImplementedError

    @abstractmethod
    def analyze_callable_args(self, arglist: TypeList) -> Optional[Tuple[List[Type],
                                                                         List[int],
                                                                         List[Optional[str]]]]:
        raise NotImplementedError


# A context for a hook that semantically analyzes an unbound type.
AnalyzeTypeContext = NamedTuple(
    'AnalyzeTypeContext', [
        ('type', UnboundType),  # Type to analyze
        ('context', Context),
        ('api', TypeAnalyzerPluginInterface)])


class CheckerPluginInterface:
    """Interface for accessing type checker functionality in plugins."""

    msg = None  # type: MessageBuilder

    @abstractmethod
    def named_generic_type(self, name: str, args: List[Type]) -> Instance:
        raise NotImplementedError


class SemanticAnalyzerPluginInterface:
    """Interface for accessing semantic analyzer functionality in plugins."""

    @abstractmethod
    def named_type(self, qualified_name: str, args: Optional[List[Type]] = None) -> Instance:
        raise NotImplementedError

    @abstractmethod
    def parse_bool(self, expr: Expression) -> Optional[bool]:
        raise NotImplementedError

    @abstractmethod
    def fail(self, msg: str, ctx: Context, serious: bool = False, *,
             blocker: bool = False) -> None:
        raise NotImplementedError


# A context for a function hook that infers the return type of a function with
# a special signature.
#
# A no-op callback would just return the inferred return type, but a useful
# callback at least sometimes can infer a more precise type.
FunctionContext = NamedTuple(
    'FunctionContext', [
        ('arg_types', List[List[Type]]),   # List of actual caller types for each formal argument
        ('default_return_type', Type),     # Return type inferred from signature
        ('args', List[List[Expression]]),  # Actual expressions for each formal argument
        ('context', Context),
        ('api', CheckerPluginInterface)])

# A context for a method signature hook that infers a better signature for a
# method.  Note that argument types aren't available yet.  If you need them,
# you have to use a method hook instead.
MethodSigContext = NamedTuple(
    'MethodSigContext', [
        ('type', Type),                       # Base object type for method call
        ('args', List[List[Expression]]),     # Actual expressions for each formal argument
        ('default_signature', CallableType),  # Original signature of the method
        ('context', Context),
        ('api', CheckerPluginInterface)])

# A context for a method hook that infers the return type of a method with a
# special signature.
#
# This is very similar to FunctionContext (only differences are documented).
MethodContext = NamedTuple(
    'MethodContext', [
        ('type', Type),                    # Base object type for method call
        ('arg_types', List[List[Type]]),
        ('default_return_type', Type),
        ('args', List[List[Expression]]),
        ('context', Context),
        ('api', CheckerPluginInterface)])

# A context for an attribute type hook that infers the type of an attribute.
AttributeContext = NamedTuple(
    'AttributeContext', [
        ('type', Type),                # Type of object with attribute
        ('default_attr_type', Type),  # Original attribute type
        ('context', Context),
        ('api', CheckerPluginInterface)])

# A context for a class hook that modifies the class definition.
ClassDefContext = NamedTuple(
    'ClassDecoratorContext', [
        ('cls', ClassDef),       # The class definition
        ('reason', Expression),  # The expression being applied (decorator, metaclass, base class)
        ('api', SemanticAnalyzerPluginInterface)
    ])


class Plugin:
    """Base class of all type checker plugins.

    This defines a no-op plugin.  Subclasses can override some methods to
    provide some actual functionality.

    All get_ methods are treated as pure functions (you should assume that
    results might be cached).

    Look at the comments of various *Context objects for descriptions of
    various hooks.
    """

    def __init__(self, options: Options) -> None:
        self.options = options
        self.python_version = options.python_version

    def get_type_analyze_hook(self, fullname: str
                              ) -> Optional[Callable[[AnalyzeTypeContext], Type]]:
        return None

    def get_function_hook(self, fullname: str
                          ) -> Optional[Callable[[FunctionContext], Type]]:
        return None

    def get_method_signature_hook(self, fullname: str
                                  ) -> Optional[Callable[[MethodSigContext], CallableType]]:
        return None

    def get_method_hook(self, fullname: str
                        ) -> Optional[Callable[[MethodContext], Type]]:
        return None

    def get_attribute_hook(self, fullname: str
                           ) -> Optional[Callable[[AttributeContext], Type]]:
        return None

    def get_class_decorator_hook(self, fullname: str
                                 ) -> Optional[Callable[[ClassDefContext], None]]:
        return None

    def get_metaclass_hook(self, fullname: str
                           ) -> Optional[Callable[[ClassDefContext], None]]:
        return None

    def get_base_class_hook(self, fullname: str
                            ) -> Optional[Callable[[ClassDefContext], None]]:
        return None


T = TypeVar('T')


class ChainedPlugin(Plugin):
    """A plugin that represents a sequence of chained plugins.

    Each lookup method returns the hook for the first plugin that
    reports a match.

    This class should not be subclassed -- use Plugin as the base class
    for all plugins.
    """

    # TODO: Support caching of lookup results (through a LRU cache, for example).

    def __init__(self, options: Options, plugins: List[Plugin]) -> None:
        """Initialize chained plugin.

        Assume that the child plugins aren't mutated (results may be cached).
        """
        super().__init__(options)
        self._plugins = plugins

    def get_type_analyze_hook(self, fullname: str
                              ) -> Optional[Callable[[AnalyzeTypeContext], Type]]:
        return self._find_hook(lambda plugin: plugin.get_type_analyze_hook(fullname))

    def get_function_hook(self, fullname: str
                          ) -> Optional[Callable[[FunctionContext], Type]]:
        return self._find_hook(lambda plugin: plugin.get_function_hook(fullname))

    def get_method_signature_hook(self, fullname: str
                                  ) -> Optional[Callable[[MethodSigContext], CallableType]]:
        return self._find_hook(lambda plugin: plugin.get_method_signature_hook(fullname))

    def get_method_hook(self, fullname: str
                        ) -> Optional[Callable[[MethodContext], Type]]:
        return self._find_hook(lambda plugin: plugin.get_method_hook(fullname))

    def get_attribute_hook(self, fullname: str
                           ) -> Optional[Callable[[AttributeContext], Type]]:
        return self._find_hook(lambda plugin: plugin.get_attribute_hook(fullname))

    def get_class_decorator_hook(self, fullname: str
                                 ) -> Optional[Callable[[ClassDefContext], None]]:
        return self._find_hook(lambda plugin: plugin.get_class_decorator_hook(fullname))

    def get_metaclass_hook(self, fullname: str
                           ) -> Optional[Callable[[ClassDefContext], None]]:
        return self._find_hook(lambda plugin: plugin.get_metaclass_hook(fullname))

    def get_base_class_hook(self, fullname: str
                            ) -> Optional[Callable[[ClassDefContext], None]]:
        return self._find_hook(lambda plugin: plugin.get_base_class_hook(fullname))

    def _find_hook(self, lookup: Callable[[Plugin], T]) -> Optional[T]:
        for plugin in self._plugins:
            hook = lookup(plugin)
            if hook:
                return hook
        return None


class DefaultPlugin(Plugin):
    """Type checker plugin that is enabled by default."""

    def get_function_hook(self, fullname: str
                          ) -> Optional[Callable[[FunctionContext], Type]]:
        if fullname == 'contextlib.contextmanager':
            return contextmanager_callback
        elif fullname == 'builtins.open' and self.python_version[0] == 3:
            return open_callback
        return None

    def get_method_signature_hook(self, fullname: str
                                  ) -> Optional[Callable[[MethodSigContext], CallableType]]:
        if fullname == 'typing.Mapping.get':
            return typed_dict_get_signature_callback
        return None

    def get_method_hook(self, fullname: str
                        ) -> Optional[Callable[[MethodContext], Type]]:
        if fullname == 'typing.Mapping.get':
            return typed_dict_get_callback
        elif fullname == 'builtins.int.__pow__':
            return int_pow_callback
        return None

    def get_class_decorator_hook(self, fullname: str
                                 ) -> Optional[Callable[[ClassDefContext], None]]:
        if fullname in attr_class_makers:
            return attr_class_maker_callback
        return None


def open_callback(ctx: FunctionContext) -> Type:
    """Infer a better return type for 'open'.

    Infer TextIO or BinaryIO as the return value if the mode argument is not
    given or is a literal.
    """
    mode = None
    if not ctx.arg_types or len(ctx.arg_types[1]) != 1:
        mode = 'r'
    elif isinstance(ctx.args[1][0], StrExpr):
        mode = ctx.args[1][0].value
    if mode is not None:
        assert isinstance(ctx.default_return_type, Instance)
        if 'b' in mode:
            return ctx.api.named_generic_type('typing.BinaryIO', [])
        else:
            return ctx.api.named_generic_type('typing.TextIO', [])
    return ctx.default_return_type


def contextmanager_callback(ctx: FunctionContext) -> Type:
    """Infer a better return type for 'contextlib.contextmanager'."""
    # Be defensive, just in case.
    if ctx.arg_types and len(ctx.arg_types[0]) == 1:
        arg_type = ctx.arg_types[0][0]
        if (isinstance(arg_type, CallableType)
                and isinstance(ctx.default_return_type, CallableType)):
            # The stub signature doesn't preserve information about arguments so
            # add them back here.
            return ctx.default_return_type.copy_modified(
                arg_types=arg_type.arg_types,
                arg_kinds=arg_type.arg_kinds,
                arg_names=arg_type.arg_names,
                variables=arg_type.variables,
                is_ellipsis_args=arg_type.is_ellipsis_args)
    return ctx.default_return_type


def typed_dict_get_signature_callback(ctx: MethodSigContext) -> CallableType:
    """Try to infer a better signature type for TypedDict.get.

    This is used to get better type context for the second argument that
    depends on a TypedDict value type.
    """
    signature = ctx.default_signature
    if (isinstance(ctx.type, TypedDictType)
            and len(ctx.args) == 2
            and len(ctx.args[0]) == 1
            and isinstance(ctx.args[0][0], StrExpr)
            and len(signature.arg_types) == 2
            and len(signature.variables) == 1
            and len(ctx.args[1]) == 1):
        key = ctx.args[0][0].value
        value_type = ctx.type.items.get(key)
        ret_type = signature.ret_type
        if value_type:
            default_arg = ctx.args[1][0]
            if (isinstance(value_type, TypedDictType)
                    and isinstance(default_arg, DictExpr)
                    and len(default_arg.items) == 0):
                # Caller has empty dict {} as default for typed dict.
                value_type = value_type.copy_modified(required_keys=set())
            # Tweak the signature to include the value type as context. It's
            # only needed for type inference since there's a union with a type
            # variable that accepts everything.
            tv = TypeVarType(signature.variables[0])
            return signature.copy_modified(
                arg_types=[signature.arg_types[0],
                           UnionType.make_simplified_union([value_type, tv])],
                ret_type=ret_type)
    return signature


def typed_dict_get_callback(ctx: MethodContext) -> Type:
    """Infer a precise return type for TypedDict.get with literal first argument."""
    if (isinstance(ctx.type, TypedDictType)
            and len(ctx.arg_types) >= 1
            and len(ctx.arg_types[0]) == 1):
        if isinstance(ctx.args[0][0], StrExpr):
            key = ctx.args[0][0].value
            value_type = ctx.type.items.get(key)
            if value_type:
                if len(ctx.arg_types) == 1:
                    return UnionType.make_simplified_union([value_type, NoneTyp()])
                elif (len(ctx.arg_types) == 2 and len(ctx.arg_types[1]) == 1
                      and len(ctx.args[1]) == 1):
                    default_arg = ctx.args[1][0]
                    if (isinstance(default_arg, DictExpr) and len(default_arg.items) == 0
                            and isinstance(value_type, TypedDictType)):
                        # Special case '{}' as the default for a typed dict type.
                        return value_type.copy_modified(required_keys=set())
                    else:
                        return UnionType.make_simplified_union([value_type, ctx.arg_types[1][0]])
            else:
                ctx.api.msg.typeddict_key_not_found(ctx.type, key, ctx.context)
                return AnyType(TypeOfAny.from_error)
    return ctx.default_return_type


def int_pow_callback(ctx: MethodContext) -> Type:
    """Infer a more precise return type for int.__pow__."""
    if (len(ctx.arg_types) == 1
            and len(ctx.arg_types[0]) == 1):
        arg = ctx.args[0][0]
        if isinstance(arg, IntExpr):
            exponent = arg.value
        elif isinstance(arg, UnaryExpr) and arg.op == '-' and isinstance(arg.expr, IntExpr):
            exponent = -arg.expr.value
        else:
            # Right operand not an int literal or a negated literal -- give up.
            return ctx.default_return_type
        if exponent >= 0:
            return ctx.api.named_generic_type('builtins.int', [])
        else:
            return ctx.api.named_generic_type('builtins.float', [])
    return ctx.default_return_type


def add_method(
        info: TypeInfo,
        method_name: str,
        args: List[Argument],
        ret_type: Type,
        self_type: Type,
        function_type: Instance) -> None:
    from mypy.semanal import set_callable_name

    first = [Argument(Var('self'), self_type, None, ARG_POS)]
    args = first + args

    arg_types = [arg.type_annotation for arg in args]
    arg_names = [arg.variable.name() for arg in args]
    arg_kinds = [arg.kind for arg in args]
    assert None not in arg_types
    signature = CallableType(cast(List[Type], arg_types), arg_kinds, arg_names,
                             ret_type, function_type)
    func = FuncDef(method_name, args, Block([]))
    func.info = info
    func.is_class = False
    func.type = set_callable_name(signature, func)
    func._fullname = info.fullname() + '.' + method_name
    info.names[method_name] = SymbolTableNode(MDEF, func)


attr_class_makers = {
    'attr.s',
    'attr.attrs',
    'attr.attributes',
}

attr_attrib_makers = {
    'attr.ib',
    'attr.attrib',
    'attr.attr'
}


def attr_class_maker_callback(ctx: ClassDefContext) -> None:
    """Add an __init__ method to classes decorated with attr.s."""
    def get_bool_argument(call: CallExpr, name: str,
                          default: Optional[bool]) -> Optional[bool]:
        for arg_name, arg_value in zip(call.arg_names, call.args):
            if arg_name == name:
                # TODO: Handle None being returned here.
                return ctx.api.parse_bool(arg_value)
        return default

    def get_argument(call: CallExpr, name: Optional[str],
                     num: Optional[int]) -> Optional[Expression]:
        for i, (attr_name, attr_value) in enumerate(zip(call.arg_names, call.args)):
            if num is not None and not attr_name and i == num:
                return attr_value
            if name and attr_name == name:
                return attr_value
        return None

    def called_function(expr: Expression) -> Optional[str]:
        if isinstance(expr, CallExpr) and isinstance(expr.callee, RefExpr):
            return expr.callee.fullname
        return None

    decorator = ctx.reason
    if isinstance(decorator, CallExpr):
        # Update init and auto_attrib if this was a call.
        init = get_bool_argument(decorator, "init", True)
        auto_attribs = get_bool_argument(decorator, "auto_attribs", False)
        cmp = get_bool_argument(decorator, "cmp", True)
    else:
        # Default values of attr.s()
        init = True
        cmp = True
        auto_attribs = False

    if not init and not cmp:
        # Nothing to add.
        return

    info = ctx.cls.info
    self_type = ctx.api.named_type(info.name())
    function_type = ctx.api.named_type('__builtins__.function')

    if init:
        # Walk the body looking for assignments.
        names = []  # type: List[str]
        types = []  # type: List[Type]
        has_default = set()  # type: Set[str]

        def add_init_argument(name: str, typ: Optional[Type], default: bool,
                              context: Context) -> None:
            if not default and has_default:
                ctx.api.fail(
                    "Non-default attributes not allowed after default attributes.",
                    context)
            if not typ:
                typ = AnyType(TypeOfAny.unannotated)

            names.append(name)
            assert typ is not None
            types.append(typ)
            if default:
                has_default.add(name)

        def is_class_var(expr: NameExpr) -> bool:
            if isinstance(expr.node, Var):
                return expr.node.is_classvar
            return False

        for stmt in ctx.cls.defs.body:
            if isinstance(stmt, AssignmentStmt) and isinstance(stmt.lvalues[0], NameExpr):
                lhs = stmt.lvalues[0]
                name = lhs.name.lstrip("_")
                typ = stmt.type

                if called_function(stmt.rvalue) in attr_attrib_makers:
                    assert isinstance(stmt.rvalue, CallExpr)
                    if not stmt.type:
                        stmt.type = AnyType(TypeOfAny.explicit)

                    # Is it an init=False argument?
                    attr_init = get_argument(stmt.rvalue, "init", 5)
                    if attr_init and ctx.api.parse_bool(attr_init) is False:
                        continue

                    # Look for default=  in the call.
                    default = get_argument(stmt.rvalue, "default", 0)
                    attr_typ = get_argument(stmt.rvalue, "type", 15)
                    if attr_typ:
                        import pdb; pdb.set_trace()
                    add_init_argument(
                        name,
                        typ,
                        bool(default),
                        stmt)
                else:
                    if auto_attribs and typ and stmt.new_syntax and not is_class_var(lhs):
                        # `x: int` (without equal sign) assigns rvalue to TempNode(AnyType())
                        has_rhs = not isinstance(stmt.rvalue, TempNode)
                        add_init_argument(name, typ, has_rhs, stmt)

        init_args = [
            Argument(Var(name, typ), typ,
                     EllipsisExpr() if name in has_default else None,
                     ARG_OPT if name in has_default else ARG_POS)
            for (name, typ) in zip(names, types)
        ]

        add_method(
            info=info,
            method_name='__init__',
            args=init_args,
            ret_type=NoneTyp(),
            self_type=self_type,
            function_type=function_type,
        )

    if cmp:
        bool_type = ctx.api.named_type('__builtins__.bool')
        args = [Argument(Var('other', self_type), self_type, None, ARG_POS)]
        for method in ['__ne__', '__eq__',
                       '__lt__', '__le__',
                       '__gt__', '__ge__']:
            add_method(
                info=info,
                method_name=method,
                args=args,
                ret_type=bool_type,
                self_type=self_type,
                function_type=function_type,
            )
