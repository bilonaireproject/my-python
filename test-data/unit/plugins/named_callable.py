from mypy.plugin import Plugin
from mypy.types import CallableType


class MyPlugin(Plugin):
    def get_function_hook(self, fullname):
        if fullname == 'm.decorator1':
            return decorator_call_hook
        if fullname == 'm._decorated':
            return decorate_hook
        return None


def decorator_call_hook(ctx):
    if isinstance(ctx.inferred_return_type, CallableType):
        return ctx.inferred_return_type.copy_modified(name='m._decorated')
    return ctx.inferred_return_type


def decorate_hook(ctx):
    if isinstance(ctx.inferred_return_type, CallableType):
        return ctx.inferred_return_type.copy_modified(
            ret_type=ctx.api.named_generic_type('builtins.str', []))
    return ctx.inferred_return_type


def plugin(version):
    return MyPlugin
