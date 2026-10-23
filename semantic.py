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
        self.functions = {}
        self.current_function = None
        self.local_scope = None

    def analyze(self, program: Program, collect_errors: bool = False) -> None:
        self.errors = []
        # Pre-pass: register function signatures
        for stmt in program.statements:
            if isinstance(stmt, FunctionDef):
                if stmt.name in self.functions:
                    err = _error(f"function '{stmt.name}' already declared", stmt)
                    self.errors.append(err)
                    if not collect_errors:
                        raise err
                    continue
                param_names = set()
                param_list = []
                for p in stmt.params:
                    if p.name in param_names:
                        err = _error(f"duplicate parameter '{p.name}' in function '{stmt.name}'", p)
                        self.errors.append(err)
                        if not collect_errors:
                            raise err
                    param_names.add(p.name)
                    param_list.append((p.var_type, p.name))
                self.functions[stmt.name] = {
                    "return_type": stmt.return_type,
                    "params": param_list,
                    "node": stmt,
                }

        for stmt in program.statements:
            try:
                self._stmt(stmt)
            except SemanticError as err:
                self.errors.append(err)
                if not collect_errors:
                    raise err

        if self.errors and not collect_errors:
            raise self.errors[0]

    def _lookup(self, name: str) -> str | None:
        if self.local_scope is not None and name in self.local_scope:
            return self.local_scope[name]
        return self.symbol_table.get(name)

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
        elif isinstance(node, FunctionDef):
            self._function_def(node)
        elif isinstance(node, ReturnStmt):
            self._return_stmt(node)
        elif isinstance(node, CallStmt):
            self._call_stmt(node)
        elif isinstance(node, ErrorNode):
            return

    def _function_def(self, node: FunctionDef) -> None:
        prev_func = self.current_function
        prev_scope = self.local_scope
        self.current_function = node
        self.local_scope = {}
        for p in node.params:
            self.local_scope[p.name] = p.var_type
        for stmt in node.body:
            self._stmt(stmt)
        self.current_function = prev_func
        self.local_scope = prev_scope

    def _return_stmt(self, node: ReturnStmt) -> None:
        if self.current_function is None:
            raise _error("return statement outside function", node)
        expected = self.current_function.return_type
        if node.expr is None:
            if expected != "void":
                raise _error(f"non-void function '{self.current_function.name}' must return {expected}", node)
        else:
            if expected == "void":
                raise _error(f"void function '{self.current_function.name}' cannot return a value", node)
            expr_type = self.type_of(node.expr)
            if expr_type != expected:
                raise _error(f"function '{self.current_function.name}' expects return type {expected}, got {expr_type}", node)

    def _check_call(self, node: CallExpr) -> str:
        if node.callee not in self.functions:
            raise _error(f"undeclared function '{node.callee}'", node)
        func_info = self.functions[node.callee]
        expected_params = func_info["params"]
        if len(node.args) != len(expected_params):
            raise _error(f"function '{node.callee}' expects {len(expected_params)} arguments, got {len(node.args)}", node)
        for arg, (expected_type, param_name) in zip(node.args, expected_params):
            arg_type = self.type_of(arg)
            if arg_type != expected_type:
                raise _error(f"argument type mismatch for parameter '{param_name}': expected {expected_type}, got {arg_type}", arg)
        return func_info["return_type"]

    def _call_stmt(self, node: CallStmt) -> None:
        self._check_call(node.call)

    def _declaration(self, node: Declaration) -> None:
        table = self.local_scope if self.local_scope is not None else self.symbol_table
        if node.name in table:
            raise _error(f"variable '{node.name}' already declared", node)
        expr_type = self.type_of(node.expr)
        if expr_type != node.var_type:
            if expr_type == "empty[]" and node.var_type.endswith("[]"):
                pass
            else:
                raise _error(f"cannot assign {expr_type} to {node.var_type}", node)
        table[node.name] = node.var_type

    def _assignment(self, node: Assignment) -> None:
        var_type = self._lookup(node.name)
        if var_type is None:
            raise _error(f"undeclared variable '{node.name}'", node)
        expr_type = self.type_of(node.expr)
        if expr_type != var_type:
            if expr_type == "empty[]" and var_type.endswith("[]"):
                return
            raise _error(f"cannot assign {expr_type} to {var_type}", node)

    def _array_assignment(self, node: ArrayAssignment) -> None:
        var_type = self._lookup(node.name)
        if var_type is None:
            raise _error(f"undeclared variable '{node.name}'", node)
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
        if isinstance(node, ErrorNode):
            return "unknown"
        if isinstance(node, Number):
            return "float" if "." in node.value else "int"
        if isinstance(node, StringLit):
            return "string"
        if isinstance(node, BoolLit):
            return "bool"
        if isinstance(node, Identifier):
            var_type = self._lookup(node.name)
            if var_type is None:
                raise _error(f"undeclared variable '{node.name}'", node)
            return var_type
        if isinstance(node, CallExpr):
            ret_type = self._check_call(node)
            if ret_type == "void":
                raise _error(f"cannot use void function '{node.callee}' in expression", node)
            return ret_type
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
