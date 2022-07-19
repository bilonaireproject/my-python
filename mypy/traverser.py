"""Generic node traverser visitor"""

from typing import List, Tuple, Optional
from mypy_extensions import mypyc_attr

from mypy.patterns import (
    AsPattern, OrPattern, ValuePattern, SequencePattern, StarredPattern, MappingPattern,
    ClassPattern
)
from mypy.visitor import NodeVisitor
from mypy.nodes import (
    AssertTypeExpr, Block, MypyFile, FuncBase, FuncItem, CallExpr, ClassDef, Decorator, FuncDef,
    ExpressionStmt, AssignmentStmt, OperatorAssignmentStmt, WhileStmt,
    ForStmt, ReturnStmt, AssertStmt, DelStmt, IfStmt, RaiseStmt,
    TryStmt, WithStmt, MatchStmt, NameExpr, MemberExpr, OpExpr, SliceExpr, CastExpr,
    RevealExpr, UnaryExpr, ListExpr, TupleExpr, DictExpr, SetExpr, IndexExpr, AssignmentExpr,
    GeneratorExpr, ListComprehension, SetComprehension, DictionaryComprehension,
    ConditionalExpr, TypeApplication, ExecStmt, Import, ImportFrom,
    LambdaExpr, ComparisonExpr, OverloadedFuncDef, YieldFromExpr,
    YieldExpr, StarExpr, BackquoteExpr, AwaitExpr, PrintStmt, SuperExpr, Node, REVEAL_TYPE,
    Expression,
)


@mypyc_attr(allow_interpreted_subclasses=True)
class TraverserVisitor(NodeVisitor[None]):
    """A parse tree visitor that traverses the parse tree during visiting.

    It does not perform any actions outside the traversal. Subclasses
    should override visit methods to perform actions during
    traversal. Calling the superclass method allows reusing the
    traversal implementation.
    """

    def __init__(self) -> None:
        pass

    # Visit methods

    def visit_mypy_file(self, o: MypyFile) -> None:
        for d in o.defs:
            d.accept(self)

    def visit_block(self, block: Block) -> None:
        for s in block.body:
            s.accept(self)

    def visit_func(self, o: FuncItem) -> None:
        if o.arguments is not None:
            for arg in o.arguments:
                init = arg.initializer
                if init is not None:
                    init.accept(self)

            for arg in o.arguments:
                self.visit_var(arg.variable)

        o.body.accept(self)

    def visit_func_def(self, o: FuncDef) -> None:
        self.visit_func(o)

    def visit_overloaded_func_def(self, o: OverloadedFuncDef) -> None:
        for item in o.items:
            item.accept(self)
        if o.impl:
            o.impl.accept(self)

    def visit_class_def(self, o: ClassDef) -> None:
        for d in o.decorators:
            d.accept(self)
        for base in o.base_type_exprs:
            base.accept(self)
        if o.metaclass:
            o.metaclass.accept(self)
        for v in o.keywords.values():
            v.accept(self)
        o.defs.accept(self)
        if o.analyzed:
            o.analyzed.accept(self)

    def visit_decorator(self, o: Decorator) -> None:
        o.func.accept(self)
        o.var.accept(self)
        for decorator in o.decorators:
            decorator.accept(self)

    def visit_expression_stmt(self, o: ExpressionStmt) -> None:
        o.expr.accept(self)

    def visit_assignment_stmt(self, o: AssignmentStmt) -> None:
        o.rvalue.accept(self)
        for l in o.lvalues:
            l.accept(self)

    def visit_operator_assignment_stmt(self, o: OperatorAssignmentStmt) -> None:
        o.rvalue.accept(self)
        o.lvalue.accept(self)

    def visit_while_stmt(self, o: WhileStmt) -> None:
        o.expr.accept(self)
        o.body.accept(self)
        if o.else_body:
            o.else_body.accept(self)

    def visit_for_stmt(self, o: ForStmt) -> None:
        o.index.accept(self)
        o.expr.accept(self)
        o.body.accept(self)
        if o.else_body:
            o.else_body.accept(self)

    def visit_return_stmt(self, o: ReturnStmt) -> None:
        if o.expr is not None:
            o.expr.accept(self)

    def visit_assert_stmt(self, o: AssertStmt) -> None:
        if o.expr is not None:
            o.expr.accept(self)
        if o.msg is not None:
            o.msg.accept(self)

    def visit_del_stmt(self, o: DelStmt) -> None:
        if o.expr is not None:
            o.expr.accept(self)

    def visit_if_stmt(self, o: IfStmt) -> None:
        for e in o.expr:
            e.accept(self)
        for b in o.body:
            b.accept(self)
        if o.else_body:
            o.else_body.accept(self)

    def visit_raise_stmt(self, o: RaiseStmt) -> None:
        if o.expr is not None:
            o.expr.accept(self)
        if o.from_expr is not None:
            o.from_expr.accept(self)

    def visit_try_stmt(self, o: TryStmt) -> None:
        o.body.accept(self)
        for i in range(len(o.types)):
            tp = o.types[i]
            if tp is not None:
                tp.accept(self)
            o.handlers[i].accept(self)
        for v in o.vars:
            if v is not None:
                v.accept(self)
        if o.else_body is not None:
            o.else_body.accept(self)
        if o.finally_body is not None:
            o.finally_body.accept(self)

    def visit_with_stmt(self, o: WithStmt) -> None:
        for i in range(len(o.expr)):
            o.expr[i].accept(self)
            targ = o.target[i]
            if targ is not None:
                targ.accept(self)
        o.body.accept(self)

    def visit_match_stmt(self, o: MatchStmt) -> None:
        o.subject.accept(self)
        for i in range(len(o.patterns)):
            o.patterns[i].accept(self)
            guard = o.guards[i]
            if guard is not None:
                guard.accept(self)
            o.bodies[i].accept(self)

    def visit_member_expr(self, o: MemberExpr) -> None:
        o.expr.accept(self)

    def visit_yield_from_expr(self, o: YieldFromExpr) -> None:
        o.expr.accept(self)

    def visit_yield_expr(self, o: YieldExpr) -> None:
        if o.expr:
            o.expr.accept(self)

    def visit_call_expr(self, o: CallExpr) -> None:
        for a in o.args:
            a.accept(self)
        o.callee.accept(self)
        if o.analyzed:
            o.analyzed.accept(self)

    def visit_op_expr(self, o: OpExpr) -> None:
        o.left.accept(self)
        o.right.accept(self)

    def visit_comparison_expr(self, o: ComparisonExpr) -> None:
        for operand in o.operands:
            operand.accept(self)

    def visit_slice_expr(self, o: SliceExpr) -> None:
        if o.begin_index is not None:
            o.begin_index.accept(self)
        if o.end_index is not None:
            o.end_index.accept(self)
        if o.stride is not None:
            o.stride.accept(self)

    def visit_cast_expr(self, o: CastExpr) -> None:
        o.expr.accept(self)

    def visit_assert_type_expr(self, o: AssertTypeExpr) -> None:
        o.expr.accept(self)

    def visit_reveal_expr(self, o: RevealExpr) -> None:
        if o.kind == REVEAL_TYPE:
            assert o.expr is not None
            o.expr.accept(self)
        else:
            # RevealLocalsExpr doesn't have an inner expression
            pass

    def visit_assignment_expr(self, o: AssignmentExpr) -> None:
        o.target.accept(self)
        o.value.accept(self)

    def visit_unary_expr(self, o: UnaryExpr) -> None:
        o.expr.accept(self)

    def visit_list_expr(self, o: ListExpr) -> None:
        for item in o.items:
            item.accept(self)

    def visit_tuple_expr(self, o: TupleExpr) -> None:
        for item in o.items:
            item.accept(self)

    def visit_dict_expr(self, o: DictExpr) -> None:
        for k, v in o.items:
            if k is not None:
                k.accept(self)
            v.accept(self)

    def visit_set_expr(self, o: SetExpr) -> None:
        for item in o.items:
            item.accept(self)

    def visit_index_expr(self, o: IndexExpr) -> None:
        o.base.accept(self)
        o.index.accept(self)
        if o.analyzed:
            o.analyzed.accept(self)

    def visit_generator_expr(self, o: GeneratorExpr) -> None:
        for index, sequence, conditions in zip(o.indices, o.sequences,
                                               o.condlists):
            sequence.accept(self)
            index.accept(self)
            for cond in conditions:
                cond.accept(self)
        o.left_expr.accept(self)

    def visit_dictionary_comprehension(self, o: DictionaryComprehension) -> None:
        for index, sequence, conditions in zip(o.indices, o.sequences,
                                               o.condlists):
            sequence.accept(self)
            index.accept(self)
            for cond in conditions:
                cond.accept(self)
        o.key.accept(self)
        o.value.accept(self)

    def visit_list_comprehension(self, o: ListComprehension) -> None:
        o.generator.accept(self)

    def visit_set_comprehension(self, o: SetComprehension) -> None:
        o.generator.accept(self)

    def visit_conditional_expr(self, o: ConditionalExpr) -> None:
        o.cond.accept(self)
        o.if_expr.accept(self)
        o.else_expr.accept(self)

    def visit_type_application(self, o: TypeApplication) -> None:
        o.expr.accept(self)

    def visit_lambda_expr(self, o: LambdaExpr) -> None:
        self.visit_func(o)

    def visit_star_expr(self, o: StarExpr) -> None:
        o.expr.accept(self)

    def visit_backquote_expr(self, o: BackquoteExpr) -> None:
        o.expr.accept(self)

    def visit_await_expr(self, o: AwaitExpr) -> None:
        o.expr.accept(self)

    def visit_super_expr(self, o: SuperExpr) -> None:
        o.call.accept(self)

    def visit_as_pattern(self, o: AsPattern) -> None:
        if o.pattern is not None:
            o.pattern.accept(self)
        if o.name is not None:
            o.name.accept(self)

    def visit_or_pattern(self, o: OrPattern) -> None:
        for p in o.patterns:
            p.accept(self)

    def visit_value_pattern(self, o: ValuePattern) -> None:
        o.expr.accept(self)

    def visit_sequence_pattern(self, o: SequencePattern) -> None:
        for p in o.patterns:
            p.accept(self)

    def visit_starred_patten(self, o: StarredPattern) -> None:
        if o.capture is not None:
            o.capture.accept(self)

    def visit_mapping_pattern(self, o: MappingPattern) -> None:
        for key in o.keys:
            key.accept(self)
        for value in o.values:
            value.accept(self)
        if o.rest is not None:
            o.rest.accept(self)

    def visit_class_pattern(self, o: ClassPattern) -> None:
        o.class_ref.accept(self)
        for p in o.positionals:
            p.accept(self)
        for v in o.keyword_values:
            v.accept(self)

    def visit_import(self, o: Import) -> None:
        for a in o.assignments:
            a.accept(self)

    def visit_import_from(self, o: ImportFrom) -> None:
        for a in o.assignments:
            a.accept(self)

    def visit_print_stmt(self, o: PrintStmt) -> None:
        for arg in o.args:
            arg.accept(self)

    def visit_exec_stmt(self, o: ExecStmt) -> None:
        o.expr.accept(self)
        if o.globals:
            o.globals.accept(self)
        if o.locals:
            o.locals.accept(self)


class ShortTraverserVisitor(TraverserVisitor):
    def skip(self, o: Node) -> bool:
        return False

    def visit_mypy_file(self, o: MypyFile) -> None:
        if self.skip(o):
            return
        super().visit_mypy_file(o)

    def visit_block(self, block: Block) -> None:
        if self.skip(block):
            return
        super().visit_block(block)

    def visit_func(self, o: FuncItem) -> None:
        if self.skip(o):
            return
        super().visit_func(o)

    def visit_func_def(self, o: FuncDef) -> None:
        if self.skip(o):
            return
        super().visit_func_def(o)

    def visit_overloaded_func_def(self, o: OverloadedFuncDef) -> None:
        if self.skip(o):
            return
        super().visit_overloaded_func_def(o)

    def visit_class_def(self, o: ClassDef) -> None:
        if self.skip(o):
            return
        super().visit_class_def(o)

    def visit_decorator(self, o: Decorator) -> None:
        if self.skip(o):
            return
        super().visit_decorator(o)

    def visit_expression_stmt(self, o: ExpressionStmt) -> None:
        if self.skip(o):
            return
        super().visit_expression_stmt(o)

    def visit_assignment_stmt(self, o: AssignmentStmt) -> None:
        if self.skip(o):
            return
        super().visit_assignment_stmt(o)

    def visit_operator_assignment_stmt(self, o: OperatorAssignmentStmt) -> None:
        if self.skip(o):
            return
        super().visit_operator_assignment_stmt(o)

    def visit_while_stmt(self, o: WhileStmt) -> None:
        if self.skip(o):
            return
        super().visit_while_stmt(o)

    def visit_for_stmt(self, o: ForStmt) -> None:
        if self.skip(o):
            return
        super().visit_for_stmt(o)

    def visit_return_stmt(self, o: ReturnStmt) -> None:
        if self.skip(o):
            return
        super().visit_return_stmt(o)

    def visit_assert_stmt(self, o: AssertStmt) -> None:
        if self.skip(o):
            return
        super().visit_assert_stmt(o)

    def visit_del_stmt(self, o: DelStmt) -> None:
        if self.skip(o):
            return
        super().visit_del_stmt(o)

    def visit_if_stmt(self, o: IfStmt) -> None:
        if self.skip(o):
            return
        super().visit_if_stmt(o)

    def visit_raise_stmt(self, o: RaiseStmt) -> None:
        if self.skip(o):
            return
        super().visit_raise_stmt(o)

    def visit_try_stmt(self, o: TryStmt) -> None:
        if self.skip(o):
            return
        super().visit_try_stmt(o)

    def visit_with_stmt(self, o: WithStmt) -> None:
        if self.skip(o):
            return
        super().visit_with_stmt(o)

    def visit_match_stmt(self, o: MatchStmt) -> None:
        if self.skip(o):
            return
        super().visit_match_stmt(o)

    def visit_member_expr(self, o: MemberExpr) -> None:
        if self.skip(o):
            return
        super().visit_member_expr(o)

    def visit_yield_from_expr(self, o: YieldFromExpr) -> None:
        if self.skip(o):
            return
        super().visit_yield_from_expr(o)

    def visit_yield_expr(self, o: YieldExpr) -> None:
        if self.skip(o):
            return
        super().visit_yield_expr(o)

    def visit_call_expr(self, o: CallExpr) -> None:
        if self.skip(o):
            return
        super().visit_call_expr(o)

    def visit_op_expr(self, o: OpExpr) -> None:
        if self.skip(o):
            return
        super().visit_op_expr(o)

    def visit_comparison_expr(self, o: ComparisonExpr) -> None:
        if self.skip(o):
            return
        super().visit_comparison_expr(o)

    def visit_slice_expr(self, o: SliceExpr) -> None:
        if self.skip(o):
            return
        super().visit_slice_expr(o)

    def visit_cast_expr(self, o: CastExpr) -> None:
        if self.skip(o):
            return
        super().visit_cast_expr(o)

    def visit_assert_type_expr(self, o: AssertTypeExpr) -> None:
        if self.skip(o):
            return
        super().visit_assert_type_expr(o)

    def visit_reveal_expr(self, o: RevealExpr) -> None:
        if self.skip(o):
            return
        super().visit_reveal_expr(o)

    def visit_assignment_expr(self, o: AssignmentExpr) -> None:
        if self.skip(o):
            return
        super().visit_assignment_expr(o)

    def visit_unary_expr(self, o: UnaryExpr) -> None:
        if self.skip(o):
            return
        super().visit_unary_expr(o)

    def visit_list_expr(self, o: ListExpr) -> None:
        if self.skip(o):
            return
        super().visit_list_expr(o)

    def visit_tuple_expr(self, o: TupleExpr) -> None:
        if self.skip(o):
            return
        super().visit_tuple_expr(o)

    def visit_dict_expr(self, o: DictExpr) -> None:
        if self.skip(o):
            return
        super().visit_dict_expr(o)

    def visit_set_expr(self, o: SetExpr) -> None:
        if self.skip(o):
            return
        super().visit_set_expr(o)

    def visit_index_expr(self, o: IndexExpr) -> None:
        if self.skip(o):
            return
        super().visit_index_expr(o)

    def visit_generator_expr(self, o: GeneratorExpr) -> None:
        if self.skip(o):
            return
        super().visit_generator_expr(o)

    def visit_dictionary_comprehension(self, o: DictionaryComprehension) -> None:
        if self.skip(o):
            return
        super().visit_dictionary_comprehension(o)

    def visit_list_comprehension(self, o: ListComprehension) -> None:
        if self.skip(o):
            return
        super().visit_list_comprehension(o)

    def visit_set_comprehension(self, o: SetComprehension) -> None:
        if self.skip(o):
            return
        super().visit_set_comprehension(o)

    def visit_conditional_expr(self, o: ConditionalExpr) -> None:
        if self.skip(o):
            return
        super().visit_conditional_expr(o)

    def visit_type_application(self, o: TypeApplication) -> None:
        if self.skip(o):
            return
        super().visit_type_application(o)

    def visit_lambda_expr(self, o: LambdaExpr) -> None:
        if self.skip(o):
            return
        super().visit_lambda_expr(o)

    def visit_star_expr(self, o: StarExpr) -> None:
        if self.skip(o):
            return
        super().visit_star_expr(o)

    def visit_backquote_expr(self, o: BackquoteExpr) -> None:
        if self.skip(o):
            return
        super().visit_backquote_expr(o)

    def visit_await_expr(self, o: AwaitExpr) -> None:
        if self.skip(o):
            return
        super().visit_await_expr(o)

    def visit_super_expr(self, o: SuperExpr) -> None:
        if self.skip(o):
            return
        super().visit_super_expr(o)

    def visit_as_pattern(self, o: AsPattern) -> None:
        if self.skip(o):
            return
        super().visit_as_pattern(o)

    def visit_or_pattern(self, o: OrPattern) -> None:
        if self.skip(o):
            return
        super().visit_or_pattern(o)

    def visit_value_pattern(self, o: ValuePattern) -> None:
        if self.skip(o):
            return
        super().visit_value_pattern(o)

    def visit_sequence_pattern(self, o: SequencePattern) -> None:
        if self.skip(o):
            return
        super().visit_sequence_pattern(o)

    def visit_starred_patten(self, o: StarredPattern) -> None:
        if self.skip(o):
            return
        super().visit_starred_patten(o)

    def visit_mapping_pattern(self, o: MappingPattern) -> None:
        if self.skip(o):
            return
        super().visit_mapping_pattern(o)

    def visit_class_pattern(self, o: ClassPattern) -> None:
        if self.skip(o):
            return
        super().visit_class_pattern(o)

    def visit_import(self, o: Import) -> None:
        if self.skip(o):
            return
        super().visit_import(o)

    def visit_import_from(self, o: ImportFrom) -> None:
        if self.skip(o):
            return
        super().visit_import_from(o)

    def visit_print_stmt(self, o: PrintStmt) -> None:
        if self.skip(o):
            return
        super().visit_print_stmt(o)

    def visit_exec_stmt(self, o: ExecStmt) -> None:
        if self.skip(o):
            return
        super().visit_exec_stmt(o)


class SearchVisitor(ShortTraverserVisitor):
    def __init__(
        self,
        line: int,
        column: int,
        end_line: int,
        end_column: int
    ) -> None:
        self.line = line
        self.column = column
        self.end_line = end_line
        self.end_column = end_column
        self.result: Optional[Expression] = None

    def skip(self, o: Node) -> bool:
        if o.line > self.line or o.line == self.line and o.column > self.column:
            return True
        if (o.end_line < self.end_line
                or o.end_line == self.end_line and o.end_column < self.end_column):
            return True
        if (
            o.line == self.line
            and o.end_line == self.end_line
            and o.column == self.column
            and o.end_column == self.end_column
        ):
            self.result = o
        if self.result is not None:
            return True


class ReturnSeeker(TraverserVisitor):
    def __init__(self) -> None:
        self.found = False

    def visit_return_stmt(self, o: ReturnStmt) -> None:
        if (o.expr is None or isinstance(o.expr, NameExpr) and o.expr.name == 'None'):
            return
        self.found = True


def find_by_location(
    tree: MypyFile,
    line: int,
    column: int,
    end_line: int,
    end_column: int
) -> Optional[Expression]:
    if end_line < line:
        raise ValueError('"end_line" must not be before "line"')
    if end_line == line and end_column <= column:
        raise ValueError('"end_column" must be after "column"')
    visitor = SearchVisitor(line, column, end_line, end_column)
    tree.accept(visitor)
    return visitor.result


def has_return_statement(fdef: FuncBase) -> bool:
    """Find if a function has a non-trivial return statement.

    Plain 'return' and 'return None' don't count.
    """
    seeker = ReturnSeeker()
    fdef.accept(seeker)
    return seeker.found


class FuncCollectorBase(TraverserVisitor):
    def __init__(self) -> None:
        self.inside_func = False

    def visit_func_def(self, defn: FuncDef) -> None:
        if not self.inside_func:
            self.inside_func = True
            super().visit_func_def(defn)
            self.inside_func = False


class YieldSeeker(FuncCollectorBase):
    def __init__(self) -> None:
        super().__init__()
        self.found = False

    def visit_yield_expr(self, o: YieldExpr) -> None:
        self.found = True


def has_yield_expression(fdef: FuncBase) -> bool:
    seeker = YieldSeeker()
    fdef.accept(seeker)
    return seeker.found


class AwaitSeeker(TraverserVisitor):
    def __init__(self) -> None:
        super().__init__()
        self.found = False

    def visit_await_expr(self, o: AwaitExpr) -> None:
        self.found = True


def has_await_expression(expr: Expression) -> bool:
    seeker = AwaitSeeker()
    expr.accept(seeker)
    return seeker.found


class ReturnCollector(FuncCollectorBase):
    def __init__(self) -> None:
        super().__init__()
        self.return_statements: List[ReturnStmt] = []

    def visit_return_stmt(self, stmt: ReturnStmt) -> None:
        self.return_statements.append(stmt)


def all_return_statements(node: Node) -> List[ReturnStmt]:
    v = ReturnCollector()
    node.accept(v)
    return v.return_statements


class YieldCollector(FuncCollectorBase):
    def __init__(self) -> None:
        super().__init__()
        self.in_assignment = False
        self.yield_expressions: List[Tuple[YieldExpr, bool]] = []

    def visit_assignment_stmt(self, stmt: AssignmentStmt) -> None:
        self.in_assignment = True
        super().visit_assignment_stmt(stmt)
        self.in_assignment = False

    def visit_yield_expr(self, expr: YieldExpr) -> None:
        self.yield_expressions.append((expr, self.in_assignment))


def all_yield_expressions(node: Node) -> List[Tuple[YieldExpr, bool]]:
    v = YieldCollector()
    node.accept(v)
    return v.yield_expressions
