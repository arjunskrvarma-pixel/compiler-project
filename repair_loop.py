import re
from dataclasses import dataclass, field

from ast_context import export_context
from ast_patch import PatchError, apply_edits
from errors import ErrorRecord
from intent import compare, fingerprint
from llm import _FALLBACK, LANGUAGE_SUMMARY, call_llm_prompt
from parser import Parser
from lexer import lex
from unparser import pretty_print
from verifier import verify_fix


@dataclass
class RepairAttempt:
    attempt_num: int
    llm_fixed_code: str
    llm_explanation: str
    verify_passed: bool
    verify_error: str
    verify_error_type: str
    edits_applied: list = field(default_factory=list)
    intent_violations: list = field(default_factory=list)
    rejected_reason: str = ""


@dataclass
class RepairResult:
    success: bool
    final_fixed_code: str
    final_explanation: str
    attempts: list
    total_attempts: int
    repair_mode: str = "text"


def _number_source(source):
    return "\n".join(f"  {i + 1} | {line}" for i, line in enumerate(source.splitlines()))


def _remove_copied_line_numbers(source):
    """Remove display-only `N | ` prefixes copied from a diagnostic prompt."""
    lines = source.splitlines()
    # Strip each independently: models sometimes omit a label on a blank line
    # or add a prose-free, unnumbered final line to an otherwise numbered fix.
    return "\n".join(re.sub(r"^\s*\d+\s*\|\s?", "", line) for line in lines)


def build_error_record_from_string(message, error_type, source):
    return ErrorRecord(error_type, message, 1, 0, "", _number_source(source), {}, "")


def _base_prompt(error):
    return f"""You are a compiler error correction assistant.
{LANGUAGE_SUMMARY}
ERROR TYPE: {error.error_type}
ERROR MESSAGE: {error.message}
LINE: {error.line}, COLUMN: {error.column}
BROKEN CODE:
{error.context}
VARIABLES IN SCOPE:
{error.symbol_table}
"""


def build_repair_prompt(original_source, current_error, attempts_history):
    history = "\n".join(f"Attempt {item.attempt_num} rejected: {item.rejected_reason or item.verify_error}" for item in attempts_history)
    return _base_prompt(current_error) + f"""PREVIOUS ATTEMPTS:
{history}
ORIGINAL SOURCE:
{_number_source(original_source)}
The `N |` prefixes above are diagnostic line labels only. Your `fixed_code` must
contain raw language source: do not include line numbers, `|`, Markdown fences,
or any explanation inside `fixed_code`.
Respond ONLY as JSON: {{"explanation": "...", "fixed_code": "..."}}
"""


def _ast_prompt(error, program, attempts):
    history = "\n".join(f"Attempt {item.attempt_num} rejected: {item.rejected_reason or item.verify_error}" for item in attempts)
    return _base_prompt(error) + f"""AST CONTEXT:
{export_context(program, error)}
PREVIOUS ATTEMPTS:
{history}
Return only JSON: {{"explanation":"...","edits":[{{"op":"SET_FIELD","target":1,"field":"op","value":"=="}}]}}
Allowed operations: REPLACE_NODE, INSERT_STMT, DELETE_NODE, SET_FIELD. Use at most 5 edits.
Node kinds: Declaration, Assignment, IfStmt(condition, body, else_body: list or IfStmt or null), WhileStmt, PrintStmt, BinaryOp(op, left, right), UnaryOp(op "-" or "!", operand), Identifier, Number, StringLit, BoolLit, Cast.
INSERT_STMT may set "branch": "else" to insert into an IfStmt else block.
"""


def _call_text(prompt, model=None):
    return call_llm_prompt(prompt, ("explanation", "fixed_code"), _FALLBACK, model=model)


def _call_ast(prompt, model=None):
    fallback = {"explanation": "LLM returned invalid format", "edits": []}
    return call_llm_prompt(prompt, ("explanation", "edits"), fallback, lambda data: isinstance(data, dict) and isinstance(data.get("explanation"), str) and isinstance(data.get("edits"), list), model=model)


def self_healing_repair(source, initial_error, max_attempts=3, repair_mode="ast", intent_guard=True, original_ast=None, model=None):
    program = original_ast or initial_error.ast
    mode = repair_mode
    # A semicolon is a token delimiter rather than a meaningful AST node.
    # Use source-level repair for this targeted syntax error, avoiding invalid
    # attempts to insert a whole statement into an otherwise valid partial AST.
    missing_semicolon = (
        initial_error.error_type == "SYNTAX"
        and initial_error.grammar_rule == "SEMI"
    )
    if mode == "ast" and (initial_error.error_type == "LEXICAL" or program is None or missing_semicolon):
        mode = "text_fallback"
    # The partial AST contains an ErrorNode at a missing semicolon, so it is
    # not a trustworthy baseline for intent comparison. Candidate verification
    # still runs the full deterministic compiler pipeline.
    original_fingerprint = (
        fingerprint(program, initial_error.target_node_id)
        if program is not None and not missing_semicolon
        else None
    )
    attempts = []
    current_error = initial_error
    for number in range(1, max_attempts + 1):
        if mode == "ast":
            data = _call_ast(_ast_prompt(current_error, program, attempts), model)
            explanation, edits = data["explanation"], data["edits"]
            try:
                candidate_ast = apply_edits(program, edits)
                candidate = pretty_print(candidate_ast)
            except (PatchError, TypeError) as error:
                attempts.append(RepairAttempt(number, "", explanation, False, str(error), "SCHEMA", edits, [], "schema"))
                current_error = build_error_record_from_string(str(error), "SCHEMA", source)
                continue
        else:
            data = _call_text(build_repair_prompt(source, current_error, attempts), model)
            explanation, candidate, edits = data["explanation"], _remove_copied_line_numbers(data["fixed_code"]), []
            if not candidate:
                attempts.append(RepairAttempt(number, "", explanation, False, "LLM returned empty fix", "SYNTAX", [], [], "malformed"))
                continue
            try:
                candidate_ast = Parser(lex(candidate)).parse()
            except Exception:
                candidate_ast = None
        valid, error_message, error_type = verify_fix(candidate)
        violations = []
        if valid and intent_guard and original_fingerprint is not None and candidate_ast is not None:
            violations = compare(original_fingerprint, fingerprint(candidate_ast, initial_error.target_node_id))
            if violations:
                valid, error_message, error_type = False, ", ".join(violations), "INTENT"
        reason = "" if valid else ("intent" if error_type == "INTENT" else error_type.lower())
        attempts.append(RepairAttempt(number, candidate, explanation, valid, error_message, error_type, edits, violations, reason))
        if valid:
            return RepairResult(True, candidate, explanation, attempts, number, mode)
        current_error = build_error_record_from_string(error_message, error_type, candidate)
    final = attempts[-1].llm_fixed_code if attempts else ""
    return RepairResult(False, final, "All repair attempts failed verification.", attempts, max_attempts, mode)
