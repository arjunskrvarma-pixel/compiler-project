from lexer import Token, lex
from ast_nodes import *

TYPE_TOKENS = ("INT", "FLOAT", "BOOL", "STRING_T", "VOID")
STMT_START = TYPE_TOKENS + ("IF", "WHILE", "PRINT", "ID", "RETURN")
EQUALITY_OPS = {"EQ": "==", "NEQ": "!="}
CMP_OPS = {"LT": "<", "GT": ">", "LE": "<=", "GE": ">="}
TERM_OPS = {"PLUS": "+", "MINUS": "-"}
FACTOR_OPS = {"STAR": "*", "SLASH": "/", "PERCENT": "%"}
UNARY_OPS = {"MINUS": "-", "NOT": "!"}


class ParseError(Exception):
    def __init__(self, message: str, line: int, col: int, expected, found):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col
        self.expected = expected
        self.found = found


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = list(tokens)
        if self.tokens:
            last = self.tokens[-1]
            eof = Token("EOF", "", last.line, last.col + len(last.value))
        else:
            eof = Token("EOF", "", 1, 1)
        self.tokens.append(eof)
        self.pos = 0
        self.errors: list[ParseError] = []

    def parse(self, partial: bool = False) -> Program:
        self.partial = partial
        statements = []
        while not self._at_end():
            if self._check("RBRACE"):
                err = self._error("statement", self._peek())
                self.errors.append(err)
                self._advance()
                continue
            try:
                statements.append(self._statement())
            except ParseError as e:
                self.errors.append(e)
                if partial:
                    statements.append(ErrorNode(e.expected, e.found, [self._peek().value], e.line, e.col))
                self._synchronize()
        if self.errors:
            if not partial:
                raise self.errors[0]
        return assign_node_ids(Program(statements))

    def _statement(self):
        if self._check(*TYPE_TOKENS):
            return self._declaration_or_function()
        if self._check("IF"):
            return self._if_stmt()
        if self._check("WHILE"):
            return self._while_stmt()
        if self._check("PRINT"):
            return self._print_stmt()
        if self._check("RETURN"):
            return self._return_stmt()
        if self._check("ID"):
            return self._id_stmt()
        raise self._error("statement", self._peek())

    def _declaration_or_function(self):
        type_tok = self._consume(*TYPE_TOKENS, expected="type")
        var_type = type_tok.value
        if self._check("LBRACKET"):
            self._consume("LBRACKET", expected="LBRACKET")
            self._consume("RBRACKET", expected="RBRACKET")
            var_type = f"{var_type}[]"
        name_tok = self._consume("ID", expected="ID")
        if self._check("LPAREN"):
            self._consume("LPAREN", expected="LPAREN")
            params = []
            if not self._check("RPAREN"):
                params.append(self._param())
                while self._check("COMMA"):
                    self._advance()
                    params.append(self._param())
            self._consume("RPAREN", expected="RPAREN")
            body = self._block()
            return FunctionDef(var_type, name_tok.value, params, body, type_tok.line, col=type_tok.col)

        if var_type == "void":
            raise self._error("variable cannot have type void", type_tok)
        self._consume("ASSIGN", expected="ASSIGN")
        expr = self._expression()
        self._consume("SEMI", expected="SEMI")
        return Declaration(var_type, name_tok.value, expr, type_tok.line, col=type_tok.col)

    def _param(self):
        p_type_tok = self._consume(*("INT", "FLOAT", "BOOL", "STRING_T"), expected="type")
        p_type = p_type_tok.value
        if self._check("LBRACKET"):
            self._consume("LBRACKET", expected="LBRACKET")
            self._consume("RBRACKET", expected="RBRACKET")
            p_type = f"{p_type}[]"
        p_name_tok = self._consume("ID", expected="ID")
        return Param(p_type, p_name_tok.value, p_type_tok.line, col=p_type_tok.col)

    def _return_stmt(self):
        tok = self._consume("RETURN", expected="RETURN")
        if self._check("SEMI"):
            self._advance()
            return ReturnStmt(None, tok.line, col=tok.col)
        expr = self._expression()
        self._consume("SEMI", expected="SEMI")
        return ReturnStmt(expr, tok.line, col=tok.col)

    def _id_stmt(self):
        name_tok = self._consume("ID", expected="ID")
        if self._check("LPAREN"):
            self._consume("LPAREN", expected="LPAREN")
            args = []
            if not self._check("RPAREN"):
                args.append(self._expression())
                while self._check("COMMA"):
                    self._advance()
                    args.append(self._expression())
            self._consume("RPAREN", expected="RPAREN")
            self._consume("SEMI", expected="SEMI")
            call = CallExpr(name_tok.value, args, name_tok.line, col=name_tok.col)
            return CallStmt(call, name_tok.line, col=name_tok.col)
        if self._check("LBRACKET"):
            self._consume("LBRACKET", expected="LBRACKET")
            index = self._expression()
            self._consume("RBRACKET", expected="RBRACKET")
            self._consume("ASSIGN", expected="ASSIGN")
            expr = self._expression()
            self._consume("SEMI", expected="SEMI")
            return ArrayAssignment(name_tok.value, index, expr, name_tok.line, col=name_tok.col)
        self._consume("ASSIGN", expected="ASSIGN")
        expr = self._expression()
        self._consume("SEMI", expected="SEMI")
        return Assignment(name_tok.value, expr, name_tok.line, col=name_tok.col)

    def _if_stmt(self):
        tok = self._consume("IF", expected="IF")
        self._consume("LPAREN", expected="LPAREN")
        cond = self._expression()
        self._consume("RPAREN", expected="RPAREN")
        body = self._block()
        else_body = None
        if self._check("ELSE"):
            self._advance()
            else_body = self._if_stmt() if self._check("IF") else self._block()
        return IfStmt(cond, body, tok.line, else_body, col=tok.col)

    def _while_stmt(self):
        tok = self._consume("WHILE", expected="WHILE")
        self._consume("LPAREN", expected="LPAREN")
        cond = self._expression()
        self._consume("RPAREN", expected="RPAREN")
        body = self._block()
        return WhileStmt(cond, body, tok.line, col=tok.col)

    def _print_stmt(self):
        tok = self._consume("PRINT", expected="PRINT")
        self._consume("LPAREN", expected="LPAREN")
        expr = self._expression()
        self._consume("RPAREN", expected="RPAREN")
        self._consume("SEMI", expected="SEMI")
        return PrintStmt(expr, tok.line, col=tok.col)

    def _block(self) -> list:
        self._consume("LBRACE", expected="LBRACE")
        body = []
        while not self._at_end() and not self._check("RBRACE"):
            try:
                if self._check("ELSE"):
                    raise self._error("RBRACE", self._peek())
                body.append(self._statement())
            except ParseError as e:
                self.errors.append(e)
                if getattr(self, "partial", False):
                    body.append(ErrorNode(e.expected, e.found, [self._peek().value], e.line, e.col))
                self._synchronize()
        self._consume("RBRACE", expected="RBRACE")
        return body

    def _expression(self):
        return self._or()

    def _binary_level(self, next_level, ops):
        node = next_level()
        while self._check(*ops):
            op_tok = self._advance()
            right = next_level()
            node = BinaryOp(ops[op_tok.type], node, right, op_tok.line, col=op_tok.col)
        return node

    def _or(self):
        return self._binary_level(self._and, {"OR": "||"})

    def _and(self):
        return self._binary_level(self._equality, {"AND": "&&"})

    def _equality(self):
        return self._binary_level(self._comparison, EQUALITY_OPS)

    def _comparison(self):
        return self._binary_level(self._term, CMP_OPS)

    def _term(self):
        return self._binary_level(self._factor, TERM_OPS)

    def _factor(self):
        return self._binary_level(self._unary, FACTOR_OPS)

    def _unary(self):
        if self._check(*UNARY_OPS):
            op_tok = self._advance()
            operand = self._unary()
            return UnaryOp(UNARY_OPS[op_tok.type], operand, op_tok.line, col=op_tok.col)
        return self._postfix()

    def _postfix(self):
        node = self._primary()
        while self._check("LBRACKET"):
            tok = self._advance()
            index = self._expression()
            self._consume("RBRACKET", expected="RBRACKET")
            node = IndexExpr(node, index, tok.line, col=tok.col)
        return node

    def _primary(self):
        tok = self._peek()
        if tok.type == "LBRACKET":
            self._advance()
            elements = []
            if not self._check("RBRACKET"):
                elements.append(self._expression())
                while self._check("COMMA"):
                    self._advance()
                    if self._check("RBRACKET"):
                        break
                    elements.append(self._expression())
            self._consume("RBRACKET", expected="RBRACKET")
            return ArrayLit(elements, tok.line, col=tok.col)
        if tok.type == "NUMBER":
            self._advance()
            return Number(tok.value, tok.line, col=tok.col)
        if tok.type == "STRING":
            self._advance()
            return StringLit(tok.value, tok.line, col=tok.col)
        if tok.type == "TRUE":
            self._advance()
            return BoolLit(True, tok.line, col=tok.col)
        if tok.type == "FALSE":
            self._advance()
            return BoolLit(False, tok.line, col=tok.col)
        if tok.type == "ID":
            self._advance()
            if self._check("LPAREN"):
                self._advance()
                args = []
                if not self._check("RPAREN"):
                    args.append(self._expression())
                    while self._check("COMMA"):
                        self._advance()
                        args.append(self._expression())
                self._consume("RPAREN", expected="RPAREN")
                return CallExpr(tok.value, args, tok.line, col=tok.col)
            return Identifier(tok.value, tok.line, col=tok.col)
        if tok.type == "LPAREN":
            self._advance()
            expr = self._expression()
            self._consume("RPAREN", expected="RPAREN")
            return expr
        if tok.type in ("INT", "FLOAT", "BOOL", "STRING_T"):
            # Cast syntax: int(expr), float(expr), bool(expr), string(expr)
            cast_type = tok.value  # "int", "float", "bool", "string"
            self._advance()
            self._consume("LPAREN", expected="LPAREN")
            inner = self._expression()
            self._consume("RPAREN", expected="RPAREN")
            return Cast(cast_type, inner, tok.line, col=tok.col)
        raise self._error("expression", tok)

    def _synchronize(self):
        while not self._at_end():
            if self._check("SEMI"):
                self._advance()
                return
            if self._check("RBRACE", *STMT_START):
                return
            self._advance()

    def _at_end(self) -> bool:
        return self._peek().type == "EOF"

    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        tok = self._peek()
        if not self._at_end():
            self.pos += 1
        return tok

    def _check(self, *types: str) -> bool:
        return self._peek().type in types

    def _consume(self, *types: str, expected: str) -> Token:
        if self._check(*types):
            return self._advance()
        raise self._error(expected, self._peek())

    def _error(self, expected, tok: Token) -> ParseError:
        found = tok.type
        msg = f"expected {expected}, found {found}"
        return ParseError(msg, tok.line, tok.col, expected, found)
