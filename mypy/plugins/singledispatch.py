from mypy.messages import format_type
from mypy.plugins.common import add_method_to_class
from mypy.nodes import (
    ARG_POS, Argument, Block, ClassDef, SymbolTable, TypeInfo, Var, Context
)
from mypy.subtypes import is_subtype
from mypy.types import (
    AnyType, CallableType, Instance, NoneType, Overloaded, Type, TypeOfAny, get_proper_type,
    FunctionLike
)
from mypy.plugin import CheckerPluginInterface, FunctionContext, MethodContext, MethodSigContext
from typing import List, NamedTuple, Optional, Sequence, TypeVar, Union
from typing_extensions import Final


class SingledispatchTypeVars(NamedTuple):
    return_type: Type
    fallback: CallableType


class RegisterCallableInfo(NamedTuple):
    register_type: Type
    singledispatch_obj: Instance


SINGLEDISPATCH_TYPE: Final = 'functools._SingleDispatchCallable'

SINGLEDISPATCH_REGISTER_METHOD: Final = f'{SINGLEDISPATCH_TYPE}.register'

SINGLEDISPATCH_CALLABLE_CALL_METHOD: Final = f'{SINGLEDISPATCH_TYPE}.__call__'


def get_singledispatch_info(typ: Instance) -> Optional[SingledispatchTypeVars]:
    if len(typ.args) == 2:
        return SingledispatchTypeVars(*typ.args)  # type: ignore
    return None


T = TypeVar('T')


def get_first_arg(args: List[List[T]]) -> Optional[T]:
    """Get the element that corresponds to the first argument passed to the function"""
    if args and args[0]:
        return args[0][0]
    return None


REGISTER_RETURN_CLASS: Final = '_SingleDispatchRegisterCallable'

REGISTER_CALLABLE_CALL_METHOD: Final = f'functools.{REGISTER_RETURN_CLASS}.__call__'


def make_fake_register_class_instance(api: CheckerPluginInterface, type_args: Sequence[Type]
                                      ) -> Instance:
    defn = ClassDef(REGISTER_RETURN_CLASS, Block([]))
    defn.fullname = f'functools.{REGISTER_RETURN_CLASS}'
    info = TypeInfo(SymbolTable(), defn, "functools")
    obj_type = api.named_generic_type('builtins.object', []).type
    info.bases = [Instance(obj_type, [])]
    info.mro = [info, obj_type]
    defn.info = info

    func_arg = Argument(Var('name'), AnyType(TypeOfAny.implementation_artifact), None, ARG_POS)
    add_method_to_class(api, defn, '__call__', [func_arg], NoneType())

    return Instance(info, type_args)


PluginContext = Union[FunctionContext, MethodContext]


def fail(ctx: PluginContext, msg: str, context: Optional[Context]) -> None:
    """Emit an error message.

    This tries to emit an error message at the location specified by `context`, falling back to the
    location specified by `ctx.context`. This is helpful when the only context information about
    where you want to put the error message may be None (like it is for `CallableType.definition`)
    and falling back to the location of the calling function is fine."""
    # TODO: figure out if there is some more reliable way of getting context information, so this
    # function isn't necessary
    if context is not None:
        err_context = context
    else:
        err_context = ctx.context
    ctx.api.fail(msg, err_context)


def create_singledispatch_function_callback(ctx: FunctionContext) -> Type:
    """Called for functools.singledispatch"""
    func_type = get_proper_type(get_first_arg(ctx.arg_types))
    if isinstance(func_type, CallableType):

        if len(func_type.arg_kinds) < 1:
            fail(
                ctx,
                'Singledispatch function requires at least one argument',
                func_type.definition,
            )
            return ctx.default_return_type

        elif not func_type.arg_kinds[0].is_positional(star=True):
            fail(
                ctx,
                'First argument to singledispatch function must be a positional argument',
                func_type.definition,
            )
            return ctx.default_return_type

        # singledispatch returns an instance of functools._SingleDispatchCallable according to
        # typeshed
        singledispatch_obj = get_proper_type(ctx.default_return_type)
        assert isinstance(singledispatch_obj, Instance)
        singledispatch_obj.args += (func_type,)

    return ctx.default_return_type


def singledispatch_register_callback(ctx: MethodContext) -> Type:
    """Called for functools._SingleDispatchCallable.register"""
    assert isinstance(ctx.type, Instance)
    # TODO: check that there's only one argument
    first_arg_type = get_proper_type(get_first_arg(ctx.arg_types))
    if isinstance(first_arg_type, (CallableType, Overloaded)) and first_arg_type.is_type_obj():
        # HACK: We received a class as an argument to register. We need to be able
        # to access the function that register is being applied to, and the typeshed definition
        # of register has it return a generic Callable, so we create a new
        # SingleDispatchRegisterCallable class, define a __call__ method, and then add a
        # plugin hook for that.

        # is_subtype doesn't work when the right type is Overloaded, so we need the
        # actual type
        register_type = first_arg_type.items[0].ret_type
        type_args = RegisterCallableInfo(register_type, ctx.type)
        register_callable = make_fake_register_class_instance(
            ctx.api,
            type_args
        )
        return register_callable
    elif isinstance(first_arg_type, CallableType):
        # TODO: do more checking for registered functions
        register_function(ctx, ctx.type, first_arg_type)
        # The typeshed stubs for register say that the function returned is Callable[..., T], even
        # though the function returned is the same as the one passed in. We return the type of the
        # function so that mypy can properly type check cases where the registered function is used
        # directly (instead of through singledispatch)
        return first_arg_type

    # fallback in case we don't recognize the arguments
    return ctx.default_return_type


def register_function(ctx: PluginContext, singledispatch_obj: Instance, func: Type,
                      register_arg: Optional[Type] = None) -> None:
    """Register a function"""

    func = get_proper_type(func)
    if not isinstance(func, CallableType):
        return
    metadata = get_singledispatch_info(singledispatch_obj)
    if metadata is None:
        # if we never added the fallback to the type variables, we already reported an error, so
        # just don't do anything here
        return
    dispatch_type = get_dispatch_type(func, register_arg)
    if dispatch_type is None:
        # TODO: report an error here that singledispatch requires at least one argument
        # (might want to do the error reporting in get_dispatch_type)
        return
    fallback = metadata.fallback

    fallback_dispatch_type = fallback.arg_types[0]
    if not is_subtype(dispatch_type, fallback_dispatch_type):

        fail(ctx, 'Dispatch type {} must be subtype of fallback function first argument {}'.format(
                format_type(dispatch_type), format_type(fallback_dispatch_type)
            ), func.definition)
        return
    return


def get_dispatch_type(func: CallableType, register_arg: Optional[Type]) -> Optional[Type]:
    if register_arg is not None:
        return register_arg
    if func.arg_types:
        return func.arg_types[0]
    return None


def call_singledispatch_function_after_register_argument(ctx: MethodContext) -> Type:
    """Called on the function after passing a type to register"""
    register_callable = ctx.type
    if isinstance(register_callable, Instance):
        type_args = RegisterCallableInfo(*register_callable.args)  # type: ignore
        func = get_first_arg(ctx.arg_types)
        if func is not None:
            register_function(ctx, type_args.singledispatch_obj, func, type_args.register_type)
            # see call to register_function in the callback for register
            return func
    return ctx.default_return_type


def call_singledispatch_function_callback(ctx: MethodSigContext) -> FunctionLike:
    """Called for functools._SingleDispatchCallable.__call__"""
    if not isinstance(ctx.type, Instance):
        return ctx.default_signature
    metadata = get_singledispatch_info(ctx.type)
    if metadata is None:
        return ctx.default_signature
    return metadata.fallback
