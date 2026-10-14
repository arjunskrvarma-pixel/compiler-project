from ast_nodes import child_nodes, index_nodes


def export_context(program, error_record):
    nodes = index_nodes(program)
    target = _target(nodes, error_record)
    if target is None:
        return f"SYMBOLS: {error_record.symbol_table}\nNo matching AST node."
    related = {target.node_id}
    parent = nodes.get(target.parent_id)
    while parent is not None:
        related.add(parent.node_id)
        parent = nodes.get(parent.parent_id)
    direct_parent = nodes.get(target.parent_id)
    if direct_parent:
        related.update(node.node_id for node in child_nodes(direct_parent))
    lines = [f"SYMBOLS: {error_record.symbol_table}"]
    for node_id in sorted(related):
        node = nodes[node_id]
        fields = []
        for key, value in vars(node).items():
            if key not in {"node_id", "parent_id", "line", "col", "body", "statements", "expr", "condition", "left", "right"}:
                fields.append(f"{key}={value!r}")
        lines.append(f"#{node_id} {type(node).__name__}({', '.join(fields)})")
    return "\n".join(lines)


def _target(nodes, error_record):
    requested = getattr(error_record, "target_node_id", None)
    if requested in nodes:
        return nodes[requested]
    matching = [node for node in nodes.values() if node.line == error_record.line and type(node).__name__ != "Program"]
    return min(matching, key=lambda node: abs(node.col - error_record.column)) if matching else None
