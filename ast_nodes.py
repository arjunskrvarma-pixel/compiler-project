from dataclasses import dataclass, field, fields, is_dataclass


@dataclass
class Program:
    statements: list
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    line: int = field(default=1, compare=False)
    col: int = field(default=1, compare=False)

    def __eq__(self, other):
        return isinstance(other, Program) and structural_value(self) == structural_value(other)


@dataclass
class Declaration:
    var_type: str
    name: str
    expr: object
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class Assignment:
    name: str
    expr: object
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class IfStmt:
    condition: object
    body: list
    line: int
    else_body: object = None
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class WhileStmt:
    condition: object
    body: list
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class PrintStmt:
    expr: object
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class BinaryOp:
    op: str
    left: object
    right: object
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class UnaryOp:
    op: str
    operand: object
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class Identifier:
    name: str
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class Number:
    value: str
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class StringLit:
    value: str
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class BoolLit:
    value: bool
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class Cast:
    target_type: str
    expr: object
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class ArrayLit:
    elements: list
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class IndexExpr:
    array: object
    index: object
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class ArrayAssignment:
    name: str
    index: object
    expr: object
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class Param:
    var_type: str
    name: str
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class FunctionDef:
    return_type: str
    name: str
    params: list
    body: list
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class ReturnStmt:
    expr: object
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class CallExpr:
    callee: str
    args: list
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class CallStmt:
    call: CallExpr
    line: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)
    col: int = field(default=1, compare=False)


@dataclass
class ErrorNode:
    expected: str
    found: str
    raw_tokens: list
    line: int
    col: int
    node_id: int = field(default=-1, compare=False)
    parent_id: int | None = field(default=None, compare=False)


def child_nodes(node):
    if not is_dataclass(node):
        return []
    children = []
    skipped = {"node_id", "parent_id", "line", "col", "expected", "found", "raw_tokens", "name", "value", "var_type", "op", "target_type", "return_type", "callee"}
    for item in fields(node):
        if item.name in skipped:
            continue
        value = getattr(node, item.name)
        if is_dataclass(value):
            children.append(value)
        elif isinstance(value, list):
            children.extend(value for value in value if is_dataclass(value))
    return children


def assign_node_ids(root):
    next_id = 1

    def visit(node, parent_id=None):
        nonlocal next_id
        node.node_id = next_id
        node.parent_id = parent_id
        next_id += 1
        for child in child_nodes(node):
            visit(child, node.node_id)

    visit(root)
    return root


def index_nodes(root):
    result = {}

    def visit(node):
        result[node.node_id] = node
        for child in child_nodes(node):
            visit(child)

    visit(root)
    return result


def structural_value(value):
    if is_dataclass(value):
        return (
            type(value).__name__,
            tuple(
                (item.name, structural_value(getattr(value, item.name)))
                for item in fields(value)
                if item.name not in {"node_id", "parent_id", "line", "col"}
            ),
        )
    if isinstance(value, list):
        return tuple(structural_value(item) for item in value)
    return value
