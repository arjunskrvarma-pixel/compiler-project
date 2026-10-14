"""Runs benchmark repairs in all text/AST and intent-guard configurations."""
import argparse
import json
import time
from pathlib import Path

from ast_nodes import index_nodes
from errors import build_error_record
from lexer import LexError, lex
from parser import ParseError, Parser
from repair_loop import self_healing_repair
from semantic import SemanticAnalyzer, SemanticError


def _compile_for_repair(source):
    analyzer = SemanticAnalyzer()
    ast = None
    try:
        ast = Parser(lex(source)).parse()
        analyzer.analyze(ast)
        return None, dict(analyzer.symbol_table), ast
    except (LexError, ParseError, SemanticError) as error:
        if isinstance(error, ParseError):
            try:
                ast = Parser(lex(source)).parse(partial=True)
            except LexError:
                ast = None
        return error, dict(analyzer.symbol_table), ast


def run_test(name, code, category, repair_mode, intent_guard, model=None):
    row = {"name": name, "category": category, "detected": False, "attempts": [], "final_success": False, "total_attempts": 0, "elapsed": 0.0, "schema_rejections": 0, "intent_rejections": 0, "malformed_output": 0}
    error, symbols, ast = _compile_for_repair(code)
    if error is None:
        row["final_success"] = True
        return row
    row["detected"] = True
    record = build_error_record(error, code, symbols)
    record.ast = ast
    if ast is not None:
        matching = [node for node in index_nodes(ast).values() if node.line == error.line and type(node).__name__ != "Program"]
        record.target_node_id = matching[0].node_id if matching else None
    started = time.time()
    result = self_healing_repair(code, record, repair_mode=repair_mode, intent_guard=intent_guard, original_ast=ast, model=model)
    row["elapsed"] = time.time() - started
    row["attempts"] = [attempt.verify_passed for attempt in result.attempts]
    row["final_success"] = result.success
    row["total_attempts"] = result.total_attempts
    row["schema_rejections"] = sum(attempt.rejected_reason == "schema" for attempt in result.attempts)
    row["intent_rejections"] = sum(attempt.rejected_reason == "intent" for attempt in result.attempts)
    row["malformed_output"] = sum(attempt.rejected_reason == "malformed" for attempt in result.attempts)
    return row


def _summary(rows):
    detected = [row for row in rows if row["detected"]]
    repaired = [row for row in detected if row["final_success"]]
    return {
        "total": len(rows), "detected": len(detected), "fixed": len(repaired),
        "success_rate": len(repaired) / max(1, len(detected)) * 100,
        "mean_attempts": sum(row["total_attempts"] for row in repaired) / max(1, len(repaired)),
        "schema_rejection_count": sum(row["schema_rejections"] for row in rows),
        "intent_rejection_count": sum(row["intent_rejections"] for row in rows),
        "token_level_malformed_output_count": sum(row["malformed_output"] for row in rows),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Ollama model for this evaluation only")
    args = parser.parse_args()
    tests_dir = Path("tests")
    expected = json.loads((tests_dir / "expected.json").read_text(encoding="utf-8"))
    output = {}
    for mode in ("text", "ast"):
        for guard in (False, True):
            key = f"{mode}_guard_{'on' if guard else 'off'}"
            rows = []
            print(f"Running {key}...")
            for filename, metadata in sorted(expected.items()):
                rows.append(run_test(filename.removesuffix(".lang"), (tests_dir / filename).read_text(encoding="utf-8"), metadata["category"], mode, guard, args.model))
            output[key] = {"rows": rows, "summary": _summary(rows)}
            print(output[key]["summary"])
    Path("results.json").write_text(json.dumps(output, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
