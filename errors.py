from dataclasses import dataclass

from lexer import LexError
from parser import ParseError
from semantic import SemanticError


@dataclass
class ErrorRecord:
    error_type: str
    message: str
    line: int
    column: int
    source_line: str
    context: str
    symbol_table: dict
    grammar_rule: str = ""
    ast: object = None
    target_node_id: int | None = None


def build_error_record(error: Exception, source: str, symbol_table: dict) -> ErrorRecord:
    if isinstance(error, LexError):
        error_type, column = "LEXICAL", error.col
        grammar_rule = ""
    elif isinstance(error, ParseError):
        error_type, column = "SYNTAX", error.col
        grammar_rule = error.expected if error.expected else ""
    elif isinstance(error, SemanticError):
        error_type, column = "SEMANTIC", getattr(error, "col", 0)
        grammar_rule = ""
    else:
        error_type, column = "SEMANTIC", 0
        grammar_rule = ""

    message = error.message
    line = error.line
    lines = source.splitlines()
    source_line = lines[line - 1] if 1 <= line <= len(lines) else ""

    start = max(0, line - 4)
    end = min(len(lines), line + 3)
    context_parts = [f"{i + 1:3d} | {lines[i]}" for i in range(start, end)]
    context = "\n".join(context_parts)

    return ErrorRecord(
        error_type=error_type,
        message=message,
        line=line,
        column=column,
        source_line=source_line,
        context=context,
        symbol_table=symbol_table,
        grammar_rule=grammar_rule,
    )
