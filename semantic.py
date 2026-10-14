from ast_nodes import *

ARITH_OPS = {"+", "-", "*", "/"}
CMP_OPS = {"==", "!=", "<", ">"}
EQ_OPS = {"==", "!="}
NUMERIC = {"int", "float"}
CMP_TYPES = {"int", "float", "bool", "string"}


class SemanticError(Exception):
    def __init__(self, message: str, line: int):
        super().__init__(message)
        self.message = message
        self.line = line


class SemanticAnalyzer:
    def __init__(self):
        self.symbol_table = {}  # name -> type str

    def analyze(self, program: Program) -> None:
        for stmt in program.statements:
            self._stmt(stmt)

    def _stmt(self, node) -> None:
        if isinstance(node, Declaration):
            self._declaration(node)
        elif isinstance(node, Assignment):
            self._assignment(node)
        elif isinstance(node, IfStmt):
            self._if_stmt(node)
        elif isinstance(node, WhileStmt):
            self._while_stmt(node)
        elif isinstance(node, PrintStmt):
            self.type_of(node.expr)  # any type is fine

    def _declaration(self, node: Declaration) -> None:
        if node.name in self.symbol_table:
            raise SemanticError(f"variable '{node.name}' already declared", node.line)
        expr_type = self.type_of(node.expr)
        if expr_type != node.var_type:
            raise SemanticError(
                f"cannot assign {expr_type} to {node.var_type}", node.line
            )
        self.symbol_table[node.name] = node.var_type

    def _assignment(self, node: Assignment) -> None:
        if node.name not in self.symbol_table:
            raise SemanticError(f"undeclared variable '{node.name}'", node.line)
        var_type = self.symbol_table[node.name]
        expr_type = self.type_of(node.expr)
        if expr_type != var_type:
            raise SemanticError(
                f"cannot assign {expr_type} to {var_type}", node.line
            )

    def _if_stmt(self, node: IfStmt) -> None:
        cond_type = self.type_of(node.condition)
        if cond_type != "bool":
            raise SemanticError(f"condition must be bool, got {cond_type}", node.line)
        for stmt in node.body:
            self._stmt(stmt)

    def _while_stmt(self, node: WhileStmt) -> None:
        cond_type = self.type_of(node.condition)
        if cond_type != "bool":
            raise SemanticError(f"condition must be bool, got {cond_type}", node.line)
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
                raise SemanticError(f"undeclared variable '{node.name}'", node.line)
            return self.symbol_table[node.name]
        if isinstance(node, BinaryOp):
            return self._binary_type(node)
        if isinstance(node, Cast):
            inner = self.type_of(node.expr)
            target = node.target_type
            if target == "string":
                raise SemanticError("cast to string not supported", node.line)
            if target in ("int", "float"):
                if inner not in ("int", "float"):
                    raise SemanticError(
                        f"cannot cast {inner} to {target}", node.line)
                return target
            if target == "bool":
                if inner not in ("int", "bool"):
                    raise SemanticError(
                        f"cannot cast {inner} to {target}", node.line)
                return target
            raise SemanticError(f"unknown cast type {target}", node.line)
        raise SemanticError("unknown expression", getattr(node, "line", 0))

    def _binary_type(self, node: BinaryOp) -> str:
        left = self.type_of(node.left)
        right = self.type_of(node.right)
        op = node.op

        if op in ARITH_OPS:
            if left not in NUMERIC or right not in NUMERIC:
                raise SemanticError(
                    f"cannot apply '{op}' to {left} and {right}", node.line
                )
            if left == "float" or right == "float":
                return "float"
            return "int"

        if op in CMP_OPS:
            if left != right:
                raise SemanticError(
                    f"cannot apply '{op}' to {left} and {right}", node.line
                )
            if left not in CMP_TYPES:
                raise SemanticError(
                    f"cannot apply '{op}' to {left} and {right}", node.line
                )
            if left == "string" and op not in EQ_OPS:
                raise SemanticError(
                    f"cannot apply '{op}' to {left} and {right}", node.line
                )
            return "bool"

        raise SemanticError(f"unknown operator '{op}'", node.line)
