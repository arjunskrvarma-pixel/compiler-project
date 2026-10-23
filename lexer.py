import re
from dataclasses import dataclass


KEYWORDS = {
    "int": "INT",
    "float": "FLOAT",
    "bool": "BOOL",
    "string": "STRING_T",
    "if": "IF",
    "else": "ELSE",
    "while": "WHILE",
    "print": "PRINT",
    "void": "VOID",
    "return": "RETURN",
    "true": "TRUE",
    "false": "FALSE",
}

OPS = [
    ("==", "EQ"),
    ("!=", "NEQ"),
    ("<=", "LE"),
    (">=", "GE"),
    ("&&", "AND"),
    ("||", "OR"),
    ("!", "NOT"),
    ("%", "PERCENT"),
    ("+", "PLUS"),
    ("-", "MINUS"),
    ("*", "STAR"),
    ("/", "SLASH"),
    ("<", "LT"),
    (">", "GT"),
    ("=", "ASSIGN"),
    ("(", "LPAREN"),
    (")", "RPAREN"),
    ("{", "LBRACE"),
    ("}", "RBRACE"),
    ("[", "LBRACKET"),
    ("]", "RBRACKET"),
    (",", "COMMA"),
    (";", "SEMI"),
]

_WS = re.compile(r"[ \t\r]+")
_ID = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_NUM = re.compile(r"\d+(?:\.\d+)?")
_BAD_NUM = re.compile(r"[a-zA-Z0-9_.]")


@dataclass
class Token:
    type: str
    value: str
    line: int
    col: int


class LexError(Exception):
    def __init__(self, message: str, line: int, col: int):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col


def lex(source: str, errors: list | None = None) -> list[Token]:
    tokens: list[Token] = []
    i, n = 0, len(source)
    line, col = 1, 1

    while i < n:
        if source[i] == "\n":
            i += 1
            line += 1
            col = 1
            continue

        m = _WS.match(source, i)
        if m:
            i = m.end()
            col += len(m.group())
            continue

        if source.startswith("//", i):
            while i < n and source[i] != "\n":
                i += 1
            continue

        start_line, start_col = line, col

        if source[i] == '"':
            j = i + 1
            col += 1  # opening quote
            while j < n and source[j] != '"':
                if source[j] == "\n":
                    line += 1
                    col = 1
                else:
                    col += 1
                j += 1
            if j >= n:
                if errors is not None:
                    errors.append(LexError("unterminated string", start_line, start_col))
                    tokens.append(Token("STRING", source[i:j], start_line, start_col))
                    i = j
                    continue
                raise LexError("unterminated string", start_line, start_col)
            lexeme = source[i : j + 1]
            tokens.append(Token("STRING", lexeme, start_line, start_col))
            i = j + 1
            col += 1  # closing quote
            continue

        m = _ID.match(source, i)
        if m:
            lexeme = m.group()
            tok_type = KEYWORDS.get(lexeme, "ID")
            tokens.append(Token(tok_type, lexeme, start_line, start_col))
            i = m.end()
            col += len(lexeme)
            continue

        m = _NUM.match(source, i)
        if m:
            if m.end() < n and _BAD_NUM.match(source[m.end()]):
                if errors is not None:
                    errors.append(LexError("malformed number", start_line, start_col))
                    end_j = m.end()
                    while end_j < n and _BAD_NUM.match(source[end_j]):
                        end_j += 1
                    bad_lexeme = source[i:end_j]
                    tokens.append(Token("ID", bad_lexeme, start_line, start_col))
                    i = end_j
                    col += len(bad_lexeme)
                    continue
                raise LexError("malformed number", start_line, start_col)
            lexeme = m.group()
            tokens.append(Token("NUMBER", lexeme, start_line, start_col))
            i = m.end()
            col += len(lexeme)
            continue

        matched = False
        for op, tok_type in OPS:
            if source.startswith(op, i):
                tokens.append(Token(tok_type, op, start_line, start_col))
                i += len(op)
                col += len(op)
                matched = True
                break
        if matched:
            continue

        if errors is not None:
            errors.append(LexError(f"illegal character {source[i]!r}", start_line, start_col))
            i += 1
            col += 1
            continue

        raise LexError(f"illegal character {source[i]!r}", start_line, start_col)

    return tokens
