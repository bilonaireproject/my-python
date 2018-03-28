"""Strip/reset AST in-place to match state after semantic analysis pass 1.

Fine-grained incremental mode reruns semantic analysis (passes 2 and 3)
and type checking for *existing* AST nodes (targets) when changes are
propagated using fine-grained dependencies.  AST nodes attributes are
often changed during semantic analysis passes 2 and 3, and running
semantic analysis again on those nodes would produce incorrect
results, since these passes aren't idempotent. This pass resets AST
nodes to reflect the state after semantic analysis pass 1, so that we
can rerun semantic analysis.

(The above is in contrast to behavior with modules that have source code
changes, for which we reparse the entire module and reconstruct a fresh
AST. No stripping is required in this case. Both modes of operation should
have the same outcome.)

Notes:

* This is currently pretty fragile, as we must carefully undo whatever
  changes can be made in semantic analysis passes 2 and 3, including changes
  to symbol tables.

* We reuse existing AST nodes because it makes it relatively straightforward
  to reprocess only a single target within a module efficiently. If there
  was a way to parse a single target within a file, in time proportional to
  the size of the target, we'd rather create fresh AST nodes than strip them.
  Alas, no such facility exists and building it is non-trivial.

* Currently we don't actually reset all changes, but only those known to affect
  non-idempotent semantic analysis behavior.
  TODO: It would be more principled and less fragile to reset everything
      changed in semantic analysis pass 2 and later.

* Reprocessing may recreate AST nodes (such as Var nodes, and TypeInfo nodes
  created with assignment statements) that will get different identities from
  the original AST. Thus running an AST merge is necessary after stripping,
  even though some identities are preserved.
"""

import contextlib
from typing import Union, Iterator, Optional

from mypy.nodes import (
    Node, FuncDef, NameExpr, MemberExpr, RefExpr, MypyFile, FuncItem, ClassDef, AssignmentStmt,
    ImportFrom, Import, TypeInfo, SymbolTable, Var, CallExpr, Decorator, OverloadedFuncDef,
    SuperExpr, UNBOUND_IMPORTED, GDEF, MDEF, IndexExpr, SymbolTableNode, ImportAll, TupleExpr,
    ListExpr
)
from mypy.semanal_shared import create_indirect_imported_name
from mypy.traverser import TraverserVisitor
from mypy.types import CallableType


def strip_target(node: Union[MypyFile, FuncItem, OverloadedFuncDef]) -> None:
    """Reset a fine-grained incremental target to state after semantic analysis pass 1.

    NOTE: Currently we opportunistically only reset changes that are known to otherwise
        cause trouble.
    """
    visitor = NodeStripVisitor()
    if isinstance(node, MypyFile):
        visitor.strip_file_top_level(node)
    else:
        node.accept(visitor)


class NodeStripVisitor(TraverserVisitor):
    def __init__(self) -> None:
        self.type = None  # type: Optional[TypeInfo]
        # Currently active module/class symbol table
        self.names = None  # type: Optional[SymbolTable]
        self.file_node = None  # type: Optional[MypyFile]
        self.is_class_body = False
        # By default, process function definitions. If False, don't -- this is used for
        # processing module top levels.
        self.recurse_into_functions = True

    def strip_file_top_level(self, file_node: MypyFile) -> None:
        """Strip a module top-level (don't recursive into functions)."""
        self.names = file_node.names
        self.file_node = file_node
        self.recurse_into_functions = False
        file_node.accept(self)

    def visit_class_def(self, node: ClassDef) -> None:
        """Strip class body and type info, but don't strip methods."""
        self.strip_type_info(node.info)
        node.base_type_exprs.extend(node.removed_base_type_exprs)
        node.removed_base_type_exprs = []
        with self.enter_class(node.info):
            super().visit_class_def(node)

    def strip_type_info(self, info: TypeInfo) -> None:
        info.type_vars = []
        info.bases = []
        info.abstract_attributes = []
        info.mro = []
        info.add_type_vars()
        info.tuple_type = None
        info.typeddict_type = None
        info.tuple_type = None
        info._cache = set()
        info._cache_proper = set()
        info.declared_metaclass = None
        info.metaclass_type = None

    def visit_func_def(self, node: FuncDef) -> None:
        if not self.recurse_into_functions:
            return
        node.expanded = []
        node.type = node.unanalyzed_type
        # Type variable binder binds tvars before the type is analized.
        # It should be refactored, before that we just undo this change here.
        if node.type:
            assert isinstance(node.type, CallableType)
            node.type.variables = []
        with self.enter_method(node.info) if node.info else nothing():
            super().visit_func_def(node)

    def visit_decorator(self, node: Decorator) -> None:
        node.var.type = None
        for expr in node.decorators:
            expr.accept(self)
        if self.recurse_into_functions:
            node.func.accept(self)

    def visit_overloaded_func_def(self, node: OverloadedFuncDef) -> None:
        if not self.recurse_into_functions:
            return
        if node.impl:
            # Revert change made during semantic analysis pass 2.
            assert node.items[-1] is not node.impl
            node.items.append(node.impl)
        super().visit_overloaded_func_def(node)

    @contextlib.contextmanager
    def enter_class(self, info: TypeInfo) -> Iterator[None]:
        old_type = self.type
        old_is_class_body = self.is_class_body
        old_names = self.names
        self.type = info
        self.is_class_body = True
        self.names = info.names
        yield
        self.type = old_type
        self.is_class_body = old_is_class_body
        self.names = old_names

    @contextlib.contextmanager
    def enter_method(self, info: TypeInfo) -> Iterator[None]:
        # TODO: Update and restore self.names
        old_type = self.type
        old_is_class_body = self.is_class_body
        self.type = info
        self.is_class_body = False
        yield
        self.type = old_type
        self.is_class_body = old_is_class_body

    def visit_assignment_stmt(self, node: AssignmentStmt) -> None:
        node.type = node.unanalyzed_type
        if self.type and not self.is_class_body:
            for lvalue in node.lvalues:
                self.process_lvalue_in_method(lvalue)
        super().visit_assignment_stmt(node)

    def process_lvalue_in_method(self, lvalue: Node) -> None:
        if isinstance(lvalue, MemberExpr):
            if lvalue.is_new_def:
                # Remove defined attribute from the class symbol table. If is_new_def is
                # true for a MemberExpr, we know that it must be an assignment through
                # self, since only those can define new attributes.
                assert self.type is not None
                del self.type.names[lvalue.name]
        elif isinstance(lvalue, (TupleExpr, ListExpr)):
            for item in lvalue.items:
                self.process_lvalue_in_method(item)

    def visit_import_from(self, node: ImportFrom) -> None:
        if node.assignments:
            node.assignments = []
        else:
            # If the node is unreachable, don't reset entries: they point to something else!
            if node.is_unreachable: return
            if self.names:
                # Reset entries in the symbol table. This is necessary since
                # otherwise the semantic analyzer will think that the import
                # assigns to an existing name instead of defining a new one.
                for name, as_name in node.names:
                    imported_name = as_name or name
                    # This assert is safe since we check for self.names above.
                    assert self.file_node is not None
                    sym = create_indirect_imported_name(self.file_node,
                                                        node.id,
                                                        node.relative,
                                                        name)
                    if sym:
                        self.names[imported_name] = sym

    def visit_import(self, node: Import) -> None:
        if node.assignments:
            node.assignments = []
        else:
            # If the node is unreachable, don't reset entries: they point to something else!
            if node.is_unreachable: return
            if self.names:
                # Reset entries in the symbol table. This is necessary since
                # otherwise the semantic analyzer will think that the import
                # assigns to an existing name instead of defining a new one.
                for name, as_name in node.ids:
                    imported_name = as_name or name
                    initial = imported_name.split('.')[0]
                    symnode = self.names[initial]
                    symnode.kind = UNBOUND_IMPORTED
                    symnode.node = None

    def visit_import_all(self, node: ImportAll) -> None:
        # If the node is unreachable, we don't want to reset entries from a reachable import.
        if node.is_unreachable:
            return
        # Reset entries in the symbol table that were added through the statement.
        # (The description in visit_import is relevant here as well.)
        if self.names:
            for name in node.imported_names:
                del self.names[name]
        node.imported_names = []

    def visit_name_expr(self, node: NameExpr) -> None:
        # Global assignments are processed in semantic analysis pass 1, and we
        # only want to strip changes made in passes 2 or later.
        if not (node.kind == GDEF and node.is_new_def):
            # Remove defined attributes so that they can recreated during semantic analysis.
            if node.kind == MDEF and node.is_new_def:
                self.strip_class_attr(node.name)
            self.strip_ref_expr(node)

    def visit_member_expr(self, node: MemberExpr) -> None:
        self.strip_ref_expr(node)
        # These need to cleared for member expressions but not for other RefExprs since
        # these can change based on changed in a base class.
        node.is_new_def = False
        node.is_inferred_def = False
        if self.is_duplicate_attribute_def(node):
            # This is marked as an instance variable definition but a base class
            # defines an attribute with the same name, and we can't have
            # multiple definitions for an attribute. Defer to the base class
            # definition.
            self.strip_class_attr(node.name)
            node.def_var = None
        super().visit_member_expr(node)

    def visit_index_expr(self, node: IndexExpr) -> None:
        node.analyzed = None  # was a type alias
        super().visit_index_expr(node)

    def strip_class_attr(self, name: str) -> None:
        if self.type is not None:
            del self.type.names[name]

    def is_duplicate_attribute_def(self, node: MemberExpr) -> bool:
        if not node.is_inferred_def:
            return False
        assert self.type is not None, "Internal error: Member defined outside class"
        if node.name not in self.type.names:
            return False
        return any(info.get(node.name) is not None for info in self.type.mro[1:])

    def strip_ref_expr(self, node: RefExpr) -> None:
        node.kind = None
        node.node = None
        node.fullname = None
        node.is_new_def = False
        node.is_inferred_def = False

    def visit_call_expr(self, node: CallExpr) -> None:
        node.analyzed = None
        super().visit_call_expr(node)

    def visit_super_expr(self, node: SuperExpr) -> None:
        node.info = None
        super().visit_super_expr(node)

    # TODO: handle more node types


def is_self_member_ref(memberexpr: MemberExpr) -> bool:
    """Does memberexpr refer to an attribute of self?"""
    # TODO: Merge with is_self_member_ref in semanal.py.
    if not isinstance(memberexpr.expr, NameExpr):
        return False
    node = memberexpr.expr.node
    return isinstance(node, Var) and node.is_self


@contextlib.contextmanager
def nothing() -> Iterator[None]:
    yield
