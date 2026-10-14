from copy import deepcopy

from ast_nodes import Assignment, BinaryOp, BoolLit, Cast, Declaration, Identifier, IfStmt, Number, PrintStmt, Program, StringLit, WhileStmt, assign_node_ids, child_nodes, index_nodes

OPS = {"+", "-", "*", "/", "==", "!=", "<", ">"}
TYPES = {"int", "float", "bool", "string"}
NODE_TYPES = {
    "Program": Program, "Declaration": Declaration, "Assignment": Assignment,
    "IfStmt": IfStmt, "WhileStmt": WhileStmt, "PrintStmt": PrintStmt,
    "BinaryOp": BinaryOp, "Identifier": Identifier, "Number": Number,
    "StringLit": StringLit, "BoolLit": BoolLit, "Cast": Cast,
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
    if kind in {"IfStmt", "WhileStmt"}:
        cls = NODE_TYPES[kind]
        return cls(node_from_json(_value(data, "condition")), [node_from_json(item) for item in _list(data, "body")], line)
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
    target_type = _string(data, "target_type")
    if target_type not in TYPES:
        raise PatchError("invalid type name")
    return Cast(target_type, node_from_json(_value(data, "expr")), line)


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
        node = node_from_json(edit.get("node"))
        if not isinstance(node, (Declaration, Assignment, IfStmt, WhileStmt, PrintStmt)):
            raise PatchError("INSERT_STMT node must be a statement")
        body = parent.statements if isinstance(parent, Program) else parent.body
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
    permitted = {BinaryOp: {"op"}, Declaration: {"var_type", "name"}, Assignment: {"name"}, Identifier: {"name"}, Number: {"value"}, StringLit: {"value"}, BoolLit: {"value"}, Cast: {"target_type"}}
    if field not in permitted.get(type(target), set()):
        raise PatchError("unknown or invalid SET_FIELD field")
    if field == "op" and value not in OPS:
        raise PatchError("invalid operator")
    if field in {"var_type", "target_type"} and value not in TYPES:
        raise PatchError("invalid type name")
    if field == "value" and isinstance(target, BoolLit) and not isinstance(value, bool):
        raise PatchError("BoolLit value must be bool")
    if field in {"name", "value"} and not isinstance(target, BoolLit) and not isinstance(value, str):
        raise PatchError("SET_FIELD value must be a string")
    setattr(target, field, value)


def _replace(parent, old, new):
    for name in ("statements", "body"):
        if hasattr(parent, name) and old in getattr(parent, name):
            items = getattr(parent, name)
            items[items.index(old)] = new
            return
    for name in ("expr", "condition", "left", "right"):
        if getattr(parent, name, None) is old:
            setattr(parent, name, new)
            return
    raise PatchError("target is not attached to parent")


def _delete(parent, target):
    for name in ("statements", "body"):
        if hasattr(parent, name) and target in getattr(parent, name):
            getattr(parent, name).remove(target)
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
