import argparse
import sys
import time
from pathlib import Path

from lexer import lex, LexError
from parser import Parser, ParseError
from semantic import SemanticAnalyzer, SemanticError
from errors import build_error_record
from repair_loop import self_healing_repair


def _target_id(ast, line):
    if ast is None:
        return None
    from ast_nodes import index_nodes
    nodes = [node for node in index_nodes(ast).values() if node.line == line and type(node).__name__ != "Program"]
    return nodes[0].node_id if nodes else None


def compile_source(source: str, log_trace: bool = False, repair_mode: str = "ast", intent_guard: bool = True) -> dict:
    """Run the full pipeline. On error, trigger self-healing repair."""
    analyzer = SemanticAnalyzer()
    ast = None
    try:
        tokens = lex(source)
        ast = Parser(tokens).parse()
        analyzer.analyze(ast)
        return {"status": "ok"}
    except (LexError, ParseError, SemanticError) as e:
        record = build_error_record(e, source, dict(analyzer.symbol_table))
        if isinstance(e, ParseError):
            try:
                ast = Parser(lex(source)).parse(partial=True)
            except LexError:
                ast = None
        record.ast = ast
        record.target_node_id = _target_id(ast, e.line)

    t0 = time.time()
    result = self_healing_repair(source, record, max_attempts=3, repair_mode=repair_mode, intent_guard=intent_guard, original_ast=ast)
    elapsed = time.time() - t0

    return {
        "status": "fixed" if result.success else "failed",
        "result": result,
        "original_error": record,
        "elapsed": elapsed,
    }


def _print_attempts(result):
    for a in result.attempts:
        if a.verify_passed:
            print(f"  Attempt {a.attempt_num}: PASS")
        else:
            print(
                f"  Attempt {a.attempt_num}: FAIL "
                f"({a.verify_error_type}: {a.verify_error})"
            )


def _display_outcome(outcome: dict, source_name: str) -> None:
    print("=" * 40)
    print(f"Compiling: {source_name}")
    print("=" * 40)

    if outcome["status"] == "ok":
        print("[OK] Compiled successfully. No errors detected.")
        return

    record = outcome["original_error"]
    print(f"\nOriginal error [{record.error_type}]: {record.message}")
    print(f"  Line {record.line}, Column {record.column}")

    result = outcome["result"]

    if outcome["status"] == "fixed":
        print("\nRepair attempts:")
        _print_attempts(result)
        print(f"\n[OK] Fixed in {result.total_attempts} attempt(s).")
        print(f"Explanation: {result.final_explanation}")
        print("\nFixed code:")
        print(result.final_fixed_code)
    else:
        print("\nRepair attempts:")
        _print_attempts(result)
        print(
            f"\n[FAIL] Could not produce a verified fix after "
            f"{result.total_attempts} attempts."
        )
    print()


def _run_file(path_str: str, repair_mode: str = "ast", intent_guard: bool = True) -> None:
    path = Path(path_str)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)
    source = path.read_text(encoding="utf-8")
    outcome = compile_source(source, repair_mode=repair_mode, intent_guard=intent_guard)
    _display_outcome(outcome, path.name)


def _run_interactive(repair_mode: str = "ast", intent_guard: bool = True) -> None:
    print("Interactive mode. Type code, then a blank line to submit.")
    print("Type 'quit' on its own line to exit.\n")
    while True:
        try:
            lines = []
            while True:
                prompt = "> " if not lines else "... "
                line = input(prompt)
                if line.strip() == "quit" and not lines:
                    print("Bye.")
                    return
                if line == "":
                    break
                lines.append(line)
            if not lines:
                continue
            source = "\n".join(lines)
            outcome = compile_source(source, repair_mode=repair_mode, intent_guard=intent_guard)
            _display_outcome(outcome, "interactive input")
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", nargs="?")
    parser.add_argument("-i", "--interactive", action="store_true")
    parser.add_argument("--repair-mode", choices=("ast", "text"), default="ast")
    parser.add_argument("--intent-guard", choices=("on", "off"), default="on")
    args = parser.parse_args()
    if args.interactive:
        _run_interactive(args.repair_mode, args.intent_guard == "on")
    elif args.file:
        _run_file(args.file, args.repair_mode, args.intent_guard == "on")
    else:
        parser.error("provide a source file or --interactive")


if __name__ == "__main__":
    main()
