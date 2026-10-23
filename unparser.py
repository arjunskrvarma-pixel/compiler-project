from ast_nodes import ArrayAssignment, ArrayLit, Assignment, BinaryOp, BoolLit, Cast, Declaration, ErrorNode, Identifier, IfStmt, IndexExpr, Number, PrintStmt, Program, StringLit, UnaryOp, WhileStmt


def pretty_print(node) -> str:
    if isinstance(node, Program):
        return "\n".join(pretty_print(item) for item in node.statements)
    if isinstance(node, Declaration):
        return f"{node.var_type} {node.name} = {pretty_print(node.expr)};"
    if isinstance(node, Assignment):
        return f"{node.name} = {pretty_print(node.expr)};"
    if isinstance(node, ArrayAssignment):
        return f"{node.name}[{pretty_print(node.index)}] = {pretty_print(node.expr)};"
    if isinstance(node, IfStmt):
        text = f"if ({pretty_print(node.condition)}) {{\n{_block(node.body)}\n}}"
        if isinstance(node.else_body, IfStmt):
            text += f" else {pretty_print(node.else_body)}"
        elif node.else_body is not None:
            text += f" else {{\n{_block(node.else_body)}\n}}"
        return text
    if isinstance(node, WhileStmt):
        return f"while ({pretty_print(node.condition)}) {{\n{_block(node.body)}\n}}"
    if isinstance(node, PrintStmt):
        return f"print({pretty_print(node.expr)});"
    if isinstance(node, BinaryOp):
        return f"({pretty_print(node.left)} {node.op} {pretty_print(node.right)})"
    if isinstance(node, UnaryOp):
        return f"({node.op}{pretty_print(node.operand)})"
    if isinstance(node, Identifier):
        return node.name
    if isinstance(node, Number):
        return node.value
    if isinstance(node, StringLit):
        return node.value
    if isinstance(node, BoolLit):
        return "true" if node.value else "false"
    if isinstance(node, Cast):
        return f"{node.target_type}({pretty_print(node.expr)})"
    if isinstance(node, ArrayLit):
        return f"[{', '.join(pretty_print(item) for item in node.elements)}]"
    if isinstance(node, IndexExpr):
        return f"{pretty_print(node.array)}[{pretty_print(node.index)}]"
    if isinstance(node, ErrorNode):
        return ""
    raise TypeError(f"cannot print {type(node).__name__}")


def _block(statements):
    return "\n".join("  " + pretty_print(statement).replace("\n", "\n  ") for statement in statements)
