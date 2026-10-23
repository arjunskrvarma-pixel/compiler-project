from copy import deepcopy

from ast_nodes import ArrayAssignment, ArrayLit, Assignment, BinaryOp, BoolLit, CallExpr, CallStmt, Cast, Declaration, FunctionDef, Identifier, IfStmt, IndexExpr, Number, Param, PrintStmt, Program, ReturnStmt, StringLit, UnaryOp, WhileStmt, assign_node_ids, child_nodes, index_nodes

OPS = {"+", "-", "*", "/", "%", "==", "!=", "<", ">", "<=", ">=", "&&", "||"}
UNARY_OPS = {"-", "!"}
TYPES = {"int", "float", "bool", "string", "void", "int[]", "float[]", "bool[]", "string[]"}
NODE_TYPES = {
    "Program": Program, "Declaration": Declaration, "Assignment": Assignment,
    "ArrayAssignment": ArrayAssignment, "IfStmt": IfStmt, "WhileStmt": WhileStmt,
    "PrintStmt": PrintStmt, "BinaryOp": BinaryOp, "Identifier": Identifier,
    "Number": Number, "StringLit": StringLit, "BoolLit": BoolLit,
    "Cast": Cast, "UnaryOp": UnaryOp, "ArrayLit": ArrayLit, "IndexExpr": IndexExpr,
    "FunctionDef": FunctionDef, "ReturnStmt": ReturnStmt, "CallExpr": CallExpr,
    "CallStmt": CallStmt, "Param": Param,
}


class PatchError(ValueError):
    pass


def node_from_json(data):
    if not isinstance(data, dict) or data.get("type") not in NODE_TYPES:
        raise PatchError("unknown node type")
    kind = data["type"]
    line = data.get("line", 1)
    if not isinstance(line, int):
        raise PatchError("node line must be an integer")
    if kind == "Program":
        return Program([node_from_json(item) for item in _list(data, "statements")])
    if kind == "Declaration":
        var_type = _string(data, "var_type")
        if var_type not in TYPES:
            raise PatchError("invalid type name")
        return Declaration(var_type, _string(data, "name"), node_from_json(_value(data, "expr")), line)
    if kind == "Assignment":
        return Assignment(_string(data, "name"), node_from_json(_value(data, "expr")), line)
    if kind == "IfStmt":
        return IfStmt(node_from_json(_value(data, "condition")), _statements(data, "body"), line, _else_from_json(data.get("else_body")))
    if kind == "WhileStmt":
        return WhileStmt(node_from_json(_value(data, "condition")), _statements(data, "body"), line)
    if kind == "UnaryOp":
        op = _string(data, "op")
        if op not in UNARY_OPS:
            raise PatchError("invalid unary operator")
        return UnaryOp(op, node_from_json(_value(data, "operand")), line)
    if kind == "PrintStmt":
        return PrintStmt(node_from_json(_value(data, "expr")), line)
    if kind == "BinaryOp":
        op = _string(data, "op")
        if op not in OPS:
            raise PatchError("invalid operator")
        return BinaryOp(op, node_from_json(_value(data, "left")), node_from_json(_value(data, "right")), line)
    if kind == "Identifier":
        return Identifier(_string(data, "name"), line)
    if kind == "Number":
        return Number(_string(data, "value"), line)
    if kind == "StringLit":
        return StringLit(_string(data, "value"), line)
    if kind == "BoolLit":
        value = _value(data, "value")
        if not isinstance(value, bool):
            raise PatchError("BoolLit value must be bool")
        return BoolLit(value, line)
    if kind == "ArrayLit":
        return ArrayLit([node_from_json(item) for item in _list(data, "elements")], line)
    if kind == "IndexExpr":
        return IndexExpr(node_from_json(_value(data, "array")), node_from_json(_value(data, "index")), line)
    if kind == "ArrayAssignment":
        return ArrayAssignment(_string(data, "name"), node_from_json(_value(data, "index")), node_from_json(_value(data, "expr")), line)
    if kind == "Param":
        var_type = _string(data, "var_type")
        if var_type not in TYPES:
            raise PatchError("invalid param type")
        return Param(var_type, _string(data, "name"), line)
    if kind == "FunctionDef":
        ret_type = _string(data, "return_type")
        if ret_type not in TYPES:
            raise PatchError("invalid return type")
        params = [node_from_json(item) for item in _list(data, "params")]
        return FunctionDef(ret_type, _string(data, "name"), params, _statements(data, "body"), line)
    if kind == "ReturnStmt":
        expr = node_from_json(data["expr"]) if "expr" in data and data["expr"] is not None else None
        return ReturnStmt(expr, line)
    if kind == "CallExpr":
        args = [node_from_json(item) for item in _list(data, "args")]
        return CallExpr(_string(data, "callee"), args, line)
    if kind == "CallStmt":
        return CallStmt(node_from_json(_value(data, "call")), line)
    target_type = _string(data, "target_type")
    if target_type not in TYPES:
        raise PatchError("invalid type name")
    return Cast(target_type, node_from_json(_value(data, "expr")), line)


STATEMENT_TYPES = (Declaration, Assignment, IfStmt, WhileStmt, PrintStmt, ArrayAssignment, FunctionDef, ReturnStmt, CallStmt)


def _statements(data, key):
    result = [node_from_json(item) for item in _list(data, key)]
    if not all(isinstance(item, STATEMENT_TYPES) for item in result):
        raise PatchError(f"{key} must contain only statements")
    return result


def _else_from_json(data):
    if data is None:
        return None
    if isinstance(data, list):
        return _statements({"else_body": data}, "else_body")
    node = node_from_json(data)
    if not isinstance(node, IfStmt):
        raise PatchError("else_body must be a statement list or an IfStmt")
    return node


def _statement_list(parent, branch):
    if isinstance(parent, Program):
        return parent.statements
    if isinstance(parent, IfStmt) and branch == "else":
        if parent.else_body is None:
            parent.else_body = []
        if not isinstance(parent.else_body, list):
            raise PatchError("else branch is an else-if chain")
        return parent.else_body
    return parent.body


def apply_edits(program, edits):
    if not isinstance(edits, list) or len(edits) > 5:
        raise PatchError("edits must contain at most 5 operations")
    result = deepcopy(program)
    assign_node_ids(result)
    for edit in edits:
        _apply_one(result, edit)
    return assign_node_ids(result)


def _apply_one(root, edit):
    if not isinstance(edit, dict) or edit.get("op") not in {"REPLACE_NODE", "INSERT_STMT", "DELETE_NODE", "SET_FIELD"}:
        raise PatchError("unknown edit operation")
    nodes = index_nodes(root)
    op = edit["op"]
    if op == "INSERT_STMT":
        parent = nodes.get(edit.get("parent"))
        index = edit.get("index")
        if not isinstance(parent, (Program, IfStmt, WhileStmt)) or not isinstance(index, int):
            raise PatchError("INSERT_STMT requires a statement-list parent and integer index")
        branch = edit.get("branch", "body")
        if branch not in {"body", "else"}:
            raise PatchError("INSERT_STMT branch must be body or else")
        node = node_from_json(edit.get("node"))
        if not isinstance(node, STATEMENT_TYPES):
            raise PatchError("INSERT_STMT node must be a statement")
        body = _statement_list(parent, branch)
        if not 0 <= index <= len(body):
            raise PatchError("INSERT_STMT index out of range")
        body.insert(index, node)
        return
    target = nodes.get(edit.get("target"))
    if target is None or isinstance(target, Program):
        raise PatchError("target id is not present or cannot target Program")
    parent = nodes.get(target.parent_id)
    if parent is None:
        raise PatchError("target has no parent")
    if op == "REPLACE_NODE":
        _replace(parent, target, node_from_json(edit.get("node")))
        return
    if op == "DELETE_NODE":
        _delete(parent, target)
        return
    field = edit.get("field")
    value = edit.get("value")
    permitted = {BinaryOp: {"op"}, Declaration: {"var_type", "name"}, Assignment: {"name"}, Identifier: {"name"}, Number: {"value"}, StringLit: {"value"}, BoolLit: {"value"}, Cast: {"target_type"}, UnaryOp: {"op"}}
    if field not in permitted.get(type(target), set()):
        raise PatchError("unknown or invalid SET_FIELD field")
    if field == "op" and isinstance(target, UnaryOp) and value not in UNARY_OPS:
        raise PatchError("invalid unary operator")
    if field == "op" and isinstance(target, BinaryOp) and value not in OPS:
        raise PatchError("invalid operator")
    if field in {"var_type", "target_type"} and value not in TYPES:
        raise PatchError("invalid type name")
    if field == "value" and isinstance(target, BoolLit) and not isinstance(value, bool):
        raise PatchError("BoolLit value must be bool")
    if field in {"name", "value"} and not isinstance(target, BoolLit) and not isinstance(value, str):
        raise PatchError("SET_FIELD value must be a string")
    setattr(target, field, value)


def _index_of(items, target):
    for position, item in enumerate(items):
        if item is target:
            return position
    return None


def _replace(parent, old, new):
    for name in ("statements", "body", "else_body"):
        items = getattr(parent, name, None)
        if isinstance(items, list) and _index_of(items, old) is not None:
            if not isinstance(new, STATEMENT_TYPES):
                raise PatchError("statement can only be replaced by a statement")
            items[_index_of(items, old)] = new
            return
    if isinstance(parent, IfStmt) and parent.else_body is old:
        if not isinstance(new, IfStmt):
            raise PatchError("else-if can only be replaced by an IfStmt")
        parent.else_body = new
        return
    for name in ("expr", "condition", "left", "right", "operand"):
        if getattr(parent, name, None) is old:
            setattr(parent, name, new)
            return
    raise PatchError("target is not attached to parent")


def _delete(parent, target):
    for name in ("statements", "body", "else_body"):
        items = getattr(parent, name, None)
        if isinstance(items, list) and _index_of(items, target) is not None:
            del items[_index_of(items, target)]
            return
    if isinstance(parent, IfStmt) and parent.else_body is target:
        parent.else_body = None
        return
    raise PatchError("only statements can be deleted")


def _value(data, key):
    if key not in data:
        raise PatchError(f"missing node field {key}")
    return data[key]


def _string(data, key):
    value = _value(data, key)
    if not isinstance(value, str):
        raise PatchError(f"node field {key} must be a string")
    return value


def _list(data, key):
    value = _value(data, key)
    if not isinstance(value, list):
        raise PatchError(f"node field {key} must be a list")
    return value
