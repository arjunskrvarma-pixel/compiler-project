from dataclasses import dataclass

from ast_nodes import ArrayAssignment, Assignment, BinaryOp, BoolLit, CallExpr, CallStmt, Declaration, FunctionDef, Identifier, IfStmt, Number, PrintStmt, ReturnStmt, StringLit, UnaryOp, WhileStmt, child_nodes, index_nodes
from unparser import pretty_print


CONDITION_OPS = {"==", "!=", "<", ">", "<=", ">=", "&&", "||"}
INVERSIONS = ({"<", ">"}, {"<=", ">="}, {"<", ">="}, {">", "<="}, {"==", "!="}, {"&&", "||"})


@dataclass
class IntentFingerprint:
    skeleton: tuple
    comparisons: tuple
    assignments: tuple
    dependencies: tuple
    prints: tuple
    condition_literals: tuple


def fingerprint(program_ast, protected_region=None):
    ignored = _ignored_ids(program_ast, protected_region)
    skeleton, comparisons, assignments, dependencies, prints, literals = [], [], [], [], [], []

    def visit_condition(node):
        comparison = _comparison(node.condition)
        if comparison:
            comparisons.append((node.node_id, comparison))
        literals.extend(_condition_literals(node.condition))

    def visit_else(else_body, depth):
        if else_body is None:
            return
        if isinstance(else_body, IfStmt):
            if else_body.node_id in ignored:
                return
            skeleton.append((depth, "ELSE_IF"))
            visit_condition(else_body)
            for child in else_body.body:
                visit_stmt(child, depth + 1)
            visit_else(else_body.else_body, depth)
            return
        skeleton.append((depth, "ELSE"))
        for child in else_body:
            visit_stmt(child, depth + 1)

    def visit_stmt(node, depth=0):
        if node.node_id in ignored:
            return
        label = {Declaration: "DECL", Assignment: "ASSIGN", ArrayAssignment: "ASSIGN", IfStmt: "IF", WhileStmt: "WHILE", PrintStmt: "PRINT", FunctionDef: "FUNC", ReturnStmt: "RETURN", CallStmt: "CALL"}.get(type(node))
        if label:
            skeleton.append((depth, label))
        if isinstance(node, FunctionDef):
            for child in node.body:
                visit_stmt(child, depth + 1)
        elif isinstance(node, (IfStmt, WhileStmt)):
            visit_condition(node)
            for child in node.body:
                visit_stmt(child, depth + 1)
            if isinstance(node, IfStmt):
                visit_else(node.else_body, depth)
        elif isinstance(node, (Declaration, Assignment, ArrayAssignment)):
            assignments.append((node.node_id, node.name))
            deps = _identifiers(node.expr) | (_identifiers(node.index) if hasattr(node, "index") else set())
            ops = _operators(node.expr) | (_operators(node.index) if hasattr(node, "index") else set())
            dependencies.append((node.node_id, node.name, tuple(sorted(deps)), tuple(sorted(ops))))
        elif isinstance(node, ReturnStmt):
            if node.expr is not None:
                deps = _identifiers(node.expr)
                ops = _operators(node.expr)
                dependencies.append((node.node_id, "__return__", tuple(sorted(deps)), tuple(sorted(ops))))
        elif isinstance(node, CallStmt):
            deps = _identifiers(node.call)
            ops = _operators(node.call)
            dependencies.append((node.node_id, f"__call_{node.call.callee}__", tuple(sorted(deps)), tuple(sorted(ops))))
        elif isinstance(node, PrintStmt):
            prints.append((node.node_id, _normalized(node.expr)))

    for statement in program_ast.statements:
        visit_stmt(statement)
    return IntentFingerprint(tuple(skeleton), tuple(comparisons), tuple(assignments), tuple(dependencies), tuple(prints), tuple(literals))


def compare(original, repaired):
    violations = []
    if original.skeleton != repaired.skeleton:
        old_kinds = tuple(item[1] for item in original.skeleton)
        new_kinds = tuple(item[1] for item in repaired.skeleton)
        violations.append("CONTROL_FLOW_CHANGED" if any(kind in {"IF", "ELSE_IF", "ELSE", "WHILE"} for kind in old_kinds + new_kinds) else "STATEMENT_REMOVED")
    old_comparisons = [item[1] for item in original.comparisons]
    new_comparisons = [item[1] for item in repaired.comparisons]
    for old, new in zip(old_comparisons, new_comparisons):
        if old != new:
            if new is None or new[0] == "literal":
                violations.append("CONDITION_REPLACED")
            elif {old[0], new[0]} in INVERSIONS:
                violations.append("CONDITION_INVERTED")
            else:
                violations.append("CONTROL_FLOW_CHANGED")
    if len(new_comparisons) < len(old_comparisons):
        violations.append("CONDITION_REPLACED")
    if tuple(name for _, name in original.assignments) != tuple(name for _, name in repaired.assignments):
        violations.append("ASSIGNMENT_REMOVED")
    if tuple(item[1:] for item in original.dependencies) != tuple(item[1:] for item in repaired.dependencies):
        violations.append("DEPENDENCY_CHANGED")
    if tuple(item[1] for item in original.prints) != tuple(item[1] for item in repaired.prints):
        violations.append("PRINT_CHANGED")
    return list(dict.fromkeys(violations))


def _ignored_ids(root, protected):
    if protected is None:
        return set()
    node_id = protected.node_id if hasattr(protected, "node_id") else protected
    nodes = index_nodes(root)
    node = nodes.get(node_id)
    if node is None:
        return set()
    result = set()

    def visit(item):
        result.add(item.node_id)
        for child in child_nodes(item):
            visit(child)

    visit(node)
    return result


def _comparison(node):
    if isinstance(node, BinaryOp) and node.op in CONDITION_OPS:
        return node.op, _normalized(node.left), _normalized(node.right)
    if isinstance(node, UnaryOp) and node.op == "!":
        return "!", _normalized(node.operand), ""
    if isinstance(node, (BoolLit, Number, StringLit)):
        return ("literal", _normalized(node), "")
    return None


def _normalized(node):
    return pretty_print(node)


def _identifiers(node):
    if isinstance(node, Identifier):
        return {node.name}
    if isinstance(node, CallExpr):
        result = {node.callee}
        for arg in node.args:
            result |= _identifiers(arg)
        return result
    result = set()
    for child in child_nodes(node):
        result |= _identifiers(child)
    return result


def _operators(node):
    result = set()
    if isinstance(node, (BinaryOp, UnaryOp)):
        result.add(node.op)
    for child in child_nodes(node):
        result |= _operators(child)
    return result


def _condition_literals(node):
    if isinstance(node, (BoolLit, Number, StringLit)):
        return [_normalized(node)]
    result = []
    for child in child_nodes(node):
        result.extend(_condition_literals(child))
    return result
