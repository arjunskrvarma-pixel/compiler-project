from dataclasses import dataclass

from ast_nodes import Assignment, BinaryOp, BoolLit, Declaration, Identifier, IfStmt, Number, PrintStmt, StringLit, WhileStmt, child_nodes, index_nodes
from unparser import pretty_print


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

    def visit_stmt(node, depth=0):
        if node.node_id in ignored:
            return
        label = {Declaration: "DECL", Assignment: "ASSIGN", IfStmt: "IF", WhileStmt: "WHILE", PrintStmt: "PRINT"}.get(type(node))
        if label:
            skeleton.append((depth, label))
        if isinstance(node, (IfStmt, WhileStmt)):
            comparison = _comparison(node.condition)
            if comparison:
                comparisons.append((node.node_id, comparison))
            literals.extend(_condition_literals(node.condition))
            for child in node.body:
                visit_stmt(child, depth + 1)
        elif isinstance(node, (Declaration, Assignment)):
            assignments.append((node.node_id, node.name))
            dependencies.append((node.node_id, node.name, tuple(sorted(_identifiers(node.expr)))))
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
        violations.append("CONTROL_FLOW_CHANGED" if any(kind in {"IF", "WHILE"} for kind in old_kinds + new_kinds) else "STATEMENT_REMOVED")
    old_comparisons = [item[1] for item in original.comparisons]
    new_comparisons = [item[1] for item in repaired.comparisons]
    for old, new in zip(old_comparisons, new_comparisons):
        if old != new:
            if new is None or new[0] == "literal":
                violations.append("CONDITION_REPLACED")
            elif {old[0], new[0]} in ({"<", ">"}, {"==", "!="}):
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
    if isinstance(node, BinaryOp) and node.op in {"==", "!=", "<", ">"}:
        return node.op, _normalized(node.left), _normalized(node.right)
    if isinstance(node, (BoolLit, Number, StringLit)):
        return ("literal", _normalized(node), "")
    return None


def _normalized(node):
    return pretty_print(node)


def _identifiers(node):
    if isinstance(node, Identifier):
        return {node.name}
    result = set()
    for child in child_nodes(node):
        result |= _identifiers(child)
    return result


def _condition_literals(node):
    if isinstance(node, (BoolLit, Number, StringLit)):
        return [_normalized(node)]
    result = []
    for child in child_nodes(node):
        result.extend(_condition_literals(child))
    return result
