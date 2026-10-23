from ast_nodes import *

ARITH_OPS = {"+", "-", "*", "/"}
EQ_OPS = {"==", "!="}
REL_OPS = {"<", ">", "<=", ">="}
LOGIC_OPS = {"&&", "||"}
NUMERIC = {"int", "float"}
CMP_TYPES = {"int", "float", "bool", "string"}


class SemanticError(Exception):
    def __init__(self, message: str, line: int, col: int = 0):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col


def _error(message, node):
    return SemanticError(message, getattr(node, "line", 0), getattr(node, "col", 0))


class SemanticAnalyzer:
    def __init__(self):
        self.symbol_table = {}

    def analyze(self, program: Program) -> None:
        for stmt in program.statements:
            self._stmt(stmt)

    def _stmt(self, node) -> None:
        if isinstance(node, Declaration):
            self._declaration(node)
        elif isinstance(node, Assignment):
            self._assignment(node)
        elif isinstance(node, ArrayAssignment):
            self._array_assignment(node)
        elif isinstance(node, IfStmt):
            self._if_stmt(node)
        elif isinstance(node, WhileStmt):
            self._while_stmt(node)
        elif isinstance(node, PrintStmt):
            self.type_of(node.expr)

    def _declaration(self, node: Declaration) -> None:
        if node.name in self.symbol_table:
            raise _error(f"variable '{node.name}' already declared", node)
        expr_type = self.type_of(node.expr)
        if expr_type != node.var_type:
            if expr_type == "empty[]" and node.var_type.endswith("[]"):
                pass
            else:
                raise _error(f"cannot assign {expr_type} to {node.var_type}", node)
        self.symbol_table[node.name] = node.var_type

    def _assignment(self, node: Assignment) -> None:
        if node.name not in self.symbol_table:
            raise _error(f"undeclared variable '{node.name}'", node)
        var_type = self.symbol_table[node.name]
        expr_type = self.type_of(node.expr)
        if expr_type != var_type:
            if expr_type == "empty[]" and var_type.endswith("[]"):
                return
            raise _error(f"cannot assign {expr_type} to {var_type}", node)

    def _array_assignment(self, node: ArrayAssignment) -> None:
        if node.name not in self.symbol_table:
            raise _error(f"undeclared variable '{node.name}'", node)
        var_type = self.symbol_table[node.name]
        if not var_type.endswith("[]"):
            raise _error(f"variable '{node.name}' is not an array", node)
        elem_type = var_type[:-2]
        idx_type = self.type_of(node.index)
        if idx_type != "int":
            raise _error(f"array index must be int, got {idx_type}", node)
        expr_type = self.type_of(node.expr)
        if expr_type != elem_type:
            raise _error(f"cannot assign {expr_type} to array of {elem_type}", node)

    def _condition(self, node) -> None:
        cond_type = self.type_of(node.condition)
        if cond_type != "bool":
            raise _error(f"condition must be bool, got {cond_type}", node)

    def _if_stmt(self, node: IfStmt) -> None:
        self._condition(node)
        for stmt in node.body:
            self._stmt(stmt)
        if isinstance(node.else_body, IfStmt):
            self._if_stmt(node.else_body)
        elif node.else_body is not None:
            for stmt in node.else_body:
                self._stmt(stmt)

    def _while_stmt(self, node: WhileStmt) -> None:
        self._condition(node)
        for stmt in node.body:
            self._stmt(stmt)

    def type_of(self, node) -> str:
        if isinstance(node, Number):
            return "float" if "." in node.value else "int"
        if isinstance(node, StringLit):
            return "string"
        if isinstance(node, BoolLit):
            return "bool"
        if isinstance(node, Identifier):
            if node.name not in self.symbol_table:
                raise _error(f"undeclared variable '{node.name}'", node)
            return self.symbol_table[node.name]
        if isinstance(node, ArrayLit):
            if not node.elements:
                return "empty[]"
            elem_types = [self.type_of(e) for e in node.elements]
            first_type = elem_types[0]
            for t in elem_types[1:]:
                if t != first_type:
                    raise _error(f"inconsistent array element types: {first_type} and {t}", node)
            return f"{first_type}[]"
        if isinstance(node, IndexExpr):
            arr_type = self.type_of(node.array)
            if not arr_type.endswith("[]"):
                raise _error(f"cannot index non-array type {arr_type}", node)
            idx_type = self.type_of(node.index)
            if idx_type != "int":
                raise _error(f"array index must be int, got {idx_type}", node)
            return arr_type[:-2]
        if isinstance(node, BinaryOp):
            return self._binary_type(node)
        if isinstance(node, UnaryOp):
            return self._unary_type(node)
        if isinstance(node, Cast):
            inner = self.type_of(node.expr)
            target = node.target_type
            if target == "string":
                raise _error("cast to string not supported", node)
            if target in ("int", "float"):
                if inner not in ("int", "float"):
                    raise _error(f"cannot cast {inner} to {target}", node)
                return target
            if target == "bool":
                if inner not in ("int", "bool"):
                    raise _error(f"cannot cast {inner} to {target}", node)
                return target
            raise _error(f"unknown cast type {target}", node)
        raise _error("unknown expression", node)

    def _unary_type(self, node: UnaryOp) -> str:
        operand = self.type_of(node.operand)
        if node.op == "-":
            if operand not in NUMERIC:
                raise _error(f"cannot apply unary '-' to {operand}", node)
            return operand
        if node.op == "!":
            if operand != "bool":
                raise _error(f"cannot apply '!' to {operand}", node)
            return "bool"
        raise _error(f"unknown operator '{node.op}'", node)

    def _binary_type(self, node: BinaryOp) -> str:
        left = self.type_of(node.left)
        right = self.type_of(node.right)
        op = node.op
        mismatch = f"cannot apply '{op}' to {left} and {right}"

        if op in ARITH_OPS:
            if left not in NUMERIC or right not in NUMERIC:
                raise _error(mismatch, node)
            if left == "float" or right == "float":
                return "float"
            return "int"

        if op == "%":
            if left != "int" or right != "int":
                raise _error(mismatch, node)
            return "int"

        if op in LOGIC_OPS:
            if left != "bool" or right != "bool":
                raise _error(mismatch, node)
            return "bool"

        if op in EQ_OPS:
            if left != right or left not in CMP_TYPES:
                raise _error(mismatch, node)
            return "bool"

        if op in REL_OPS:
            if left != right or left not in NUMERIC:
                raise _error(mismatch, node)
            return "bool"

        raise _error(f"unknown operator '{op}'", node)
