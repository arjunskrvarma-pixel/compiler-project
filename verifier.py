from lexer import lex, LexError
from parser import Parser, ParseError
from semantic import SemanticAnalyzer, SemanticError


def verify_fix(fixed_code: str) -> tuple[bool, str, str]:
    try:
        tokens = lex(fixed_code)
    except LexError as e:
        return (False, e.message, "LEXICAL")

    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        return (False, e.message, "SYNTAX")

    try:
        SemanticAnalyzer().analyze(ast)
    except SemanticError as e:
        return (False, e.message, "SEMANTIC")

    return (True, "", "")