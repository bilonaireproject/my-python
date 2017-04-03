from typing import Optional, Dict, Union
from mypy.types import TypeVarDef, TypeVarId
from mypy.nodes import TypeVarExpr, SymbolTableNode


class TypeVarScope:
    """Scope that holds bindings for type variables. Node fullname -> TypeVarDef.

    Provide a parent on intitalization when you want to make a child scope."""

    def __init__(self, parent: Optional['TypeVarScope'] = None) -> None:
        self.scope = {}  # type: Dict[str, TypeVarDef]
        self.parent = parent
        self.func_id = 0
        self.class_id = 0
        if parent is not None:
            self.func_id = parent.func_id
            self.class_id = parent.class_id

    def bind_fun_tvar(self, name: str, tvar_expr: TypeVarExpr) -> TypeVarDef:
        self.func_id -= 1
        return self._bind(name, tvar_expr, self.func_id)

    def bind_class_tvar(self, name: str, tvar_expr: TypeVarExpr) -> TypeVarDef:
        self.class_id += 1
        return self._bind(name, tvar_expr, self.class_id)

    def _bind(self, name: str, tvar_expr: TypeVarExpr, i: int) -> TypeVarDef:
        tvar_def = TypeVarDef(
            name, i, values=tvar_expr.values,
            upper_bound=tvar_expr.upper_bound, variance=tvar_expr.variance,
            line=tvar_expr.line, column=tvar_expr.column)
        self.scope[tvar_expr.fullname()] = tvar_def
        return tvar_def

    def get_binding(self, item: Union[str, SymbolTableNode]) -> Optional[TypeVarDef]:
        fullname = item.fullname if isinstance(item, SymbolTableNode) else item
        if fullname in self.scope:
            return self.scope[fullname]
        elif self.parent is not None:
            return self.parent.get_binding(fullname)
        else:
            return None

    def __str__(self) -> str:
        me = ", ".join('{}: {}`{}'.format(k, v.name, v.id) for k, v in self.scope.items())
        if self.parent is None:
            return me
        return "{} <- {}".format(str(self.parent), me)
