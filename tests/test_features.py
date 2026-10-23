import pytest
from ast_nodes import ArrayAssignment, ArrayLit, ErrorNode, IndexExpr, index_nodes
from ast_patch import PatchError, apply_edits
from intent import IntentFingerprint, compare, fingerprint
from lexer import lex
from parser import Parser
from semantic import SemanticAnalyzer, SemanticError
from unparser import pretty_print
from verifier import verify_fix


def parse(source):
    return Parser(lex(source)).parse()


def test_unparser_round_trip_constructed_programs():
    sources = [
        "int x = 1;",
        "float x = 1.0; bool ok = true; string s = \"a\"; print(s);",
        "int x = 1; while (x < 3) { print(x); x = x + 1; }",
        "int x = 1; if (bool(x)) { print(float(x)); }",
    ]
    for source in sources:
        ast = parse(source)
        assert parse(pretty_print(ast)) == ast


def test_node_ids_and_partial_error_node():
    ast = parse("int x = 1; print(x);")
    assert list(index_nodes(ast)) == list(range(1, len(index_nodes(ast)) + 1))
    partial = Parser(lex("int x = ; print(1);")).parse(partial=True)
    assert any(isinstance(item, ErrorNode) for item in partial.statements)


def test_patch_operations_and_rejections():
    ast = parse("int x = 1; print(x);")
    nodes = index_nodes(ast)
    ident = next(node for node in nodes.values() if type(node).__name__ == "Identifier")
    patched = apply_edits(ast, [{"op": "REPLACE_NODE", "target": ident.node_id, "node": {"type": "Number", "value": "1"}}])
    assert "print(1);" in pretty_print(patched)
    root = index_nodes(ast)[1]
    inserted = apply_edits(ast, [{"op": "INSERT_STMT", "parent": root.node_id, "index": 1, "node": {"type": "PrintStmt", "expr": {"type": "Number", "value": "2"}}}])
    assert "print(2);" in pretty_print(inserted)
    changed = apply_edits(ast, [{"op": "SET_FIELD", "target": ident.node_id, "field": "name", "value": "y"}])
    assert "print(y);" in pretty_print(changed)
    deleted = apply_edits(ast, [{"op": "DELETE_NODE", "target": ast.statements[1].node_id}])
    assert "print" not in pretty_print(deleted)
    with __import__("pytest").raises(PatchError):
        apply_edits(ast, [{"op": "SET_FIELD", "target": ident.node_id, "field": "op", "value": "bad"}])


def test_intent_categories_and_protection():
    original = parse("int x = 1; while (x < 3) { print(x); x = x + 1; }")
    changed = parse("int x = 1; while (x > 3) { print(1); }")
    violations = compare(fingerprint(original), fingerprint(changed))
    assert "CONDITION_INVERTED" in violations
    assert "PRINT_CHANGED" in violations
    assert "ASSIGNMENT_REMOVED" in violations
    condition = original.statements[1].condition
    assert compare(fingerprint(original, condition.node_id), fingerprint(changed, condition.node_id))


def test_all_intent_violation_labels():
    base = IntentFingerprint(((0, "IF"),), ((1, ("<", "x", "3")),), ((2, "x"),), ((2, "x", ("x",)),), ((3, "x"),), ())
    changed = IntentFingerprint(((0, "WHILE"),), ((1, ("literal", "true", "")),), (), (), ((3, "1"),), ())
    labels = compare(base, changed)
    assert {"CONTROL_FLOW_CHANGED", "CONDITION_REPLACED", "ASSIGNMENT_REMOVED", "DEPENDENCY_CHANGED", "PRINT_CHANGED"}.issubset(labels)


def test_text_fallback_with_mocked_llm(monkeypatch):
    from errors import build_error_record
    from lexer import LexError
    import repair_loop
    source = "int x = 1 @ 2;"
    error = LexError("illegal character '@'", 1, 11)
    record = build_error_record(error, source, {})
    monkeypatch.setattr(repair_loop, "_call_text", lambda prompt, model=None: {"explanation": "remove @", "fixed_code": "int x = 1;"})
    result = repair_loop.self_healing_repair(source, record, repair_mode="ast")
    assert result.success and result.repair_mode == "text_fallback"


def test_missing_semicolon_uses_text_fallback(monkeypatch):
    from errors import build_error_record
    from parser import ParseError
    import repair_loop

    source = "int x = 5;\nprint(x)"
    try:
        Parser(lex(source)).parse()
    except ParseError as error:
        record = build_error_record(error, source, {})
        partial_ast = Parser(lex(source)).parse(partial=True)
    else:
        raise AssertionError("source should be missing a semicolon")

    monkeypatch.setattr(
        repair_loop,
        "_call_text",
        lambda prompt, model=None: {
            "explanation": "add the missing semicolon",
            "fixed_code": "int x = 5;\nprint(x);",
        },
    )
    result = repair_loop.self_healing_repair(
        source, record, repair_mode="ast", original_ast=partial_ast
    )
    assert result.success and result.repair_mode == "text_fallback"


def test_text_repair_removes_copied_diagnostic_line_numbers(monkeypatch):
    from errors import build_error_record
    from parser import ParseError
    import repair_loop

    source = "int x = 1;\nif (x > 0 {\n  print(x);\n}"
    try:
        Parser(lex(source)).parse()
    except ParseError as error:
        record = build_error_record(error, source, {})
    else:
        raise AssertionError("source should be missing a closing parenthesis")

    monkeypatch.setattr(
        repair_loop,
        "_call_text",
        lambda prompt, model=None: {
            "explanation": "close the condition",
            "fixed_code": "1 | int x = 1;\n2 | if (x > 0) {\n3 |   print(x);\n4 | }",
        },
    )
    result = repair_loop.self_healing_repair(source, record, repair_mode="text")
    assert result.success
    assert result.final_fixed_code == "int x = 1;\nif (x > 0) {\n  print(x);\n}"


import json
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent
CATEGORY_TYPES = {"lexical": "LEXICAL", "syntax": "SYNTAX", "semantic": "SEMANTIC"}


def diagnose(source):
    from errors import build_error_record
    from lexer import LexError
    from parser import ParseError
    from semantic import SemanticAnalyzer, SemanticError
    try:
        SemanticAnalyzer().analyze(parse(source))
    except (LexError, ParseError, SemanticError) as error:
        record = build_error_record(error, source, {})
        return record.error_type, record.line, record.column, record.message
    return None


def test_every_expected_case_is_detected_with_its_category():
    expected = json.loads((TESTS_DIR / "expected.json").read_text(encoding="utf-8"))
    for filename, metadata in expected.items():
        result = diagnose((TESTS_DIR / filename).read_text(encoding="utf-8"))
        assert result is not None, filename
        assert result[0] == CATEGORY_TYPES[metadata["category"]], filename


@pytest.mark.parametrize("path", sorted((TESTS_DIR / "ok").glob("*.lang")), ids=lambda path: path.name)
def test_ok_programs_compile_and_round_trip(path):
    source = path.read_text(encoding="utf-8")
    assert diagnose(source) is None
    ast = parse(source)
    assert parse(pretty_print(ast)) == ast


STAGE1_ERRORS = {
    "tc27.lang": ("SYNTAX", 4, 1, "expected RBRACE, found ELSE"),
    "tc28.lang": ("SYNTAX", 2, 1, "expected statement, found ELSE"),
    "tc29.lang": ("SEMANTIC", 2, 12, "cannot apply '&&' to int and bool"),
    "tc30.lang": ("SEMANTIC", 2, 10, "cannot apply '!' to int"),
    "tc31.lang": ("SEMANTIC", 1, 15, "cannot apply '%' to float and float"),
    "tc32.lang": ("SEMANTIC", 2, 9, "cannot apply unary '-' to bool"),
    "tc33.lang": ("SEMANTIC", 2, 12, "cannot apply unary '-' to string"),
    "tc34.lang": ("SEMANTIC", 2, 12, "cannot apply '<=' to string and string"),
    "tc35.lang": ("SYNTAX", 7, 4, "expected RBRACE, found EOF"),
}


@pytest.mark.parametrize("filename,expected", sorted(STAGE1_ERRORS.items()))
def test_stage1_error_positions(filename, expected):
    assert diagnose((TESTS_DIR / filename).read_text(encoding="utf-8")) == expected


def test_stage1_lexer_longest_match():
    types = [token.type for token in lex("a != !b <= >= && || % < > = !")]
    assert types == ["ID", "NEQ", "NOT", "ID", "LE", "GE", "AND", "OR", "PERCENT", "LT", "GT", "ASSIGN", "NOT"]


def test_stage1_precedence_and_else_if_shape():
    from ast_nodes import BinaryOp, IfStmt, UnaryOp
    expr = parse("bool b = !x || y && 1 + 2 * 3 % 4 <= -5 == true;").statements[0].expr
    assert isinstance(expr, BinaryOp) and expr.op == "||"
    assert isinstance(expr.left, UnaryOp) and expr.left.op == "!"
    assert expr.right.op == "&&" and expr.right.right.op == "=="
    assert expr.right.right.left.op == "<=" and isinstance(expr.right.right.left.right, UnaryOp)
    chain = parse("if (a) { print(1); } else if (b) { print(2); } else { print(3); }").statements[0]
    assert isinstance(chain.else_body, IfStmt) and isinstance(chain.else_body.else_body, list)


def test_stage1_canonical_unparse():
    ast = parse("if (a) { print(1); } else if (b) { print(-x); } else { print(!c); }")
    assert pretty_print(ast) == "if (a) {\n  print(1);\n} else if (b) {\n  print((-x));\n} else {\n  print((!c));\n}"
    assert parse(pretty_print(ast)) == ast


def test_stage1_partial_parse_recovers_inside_if():
    partial = Parser(lex("int x = 1;\nif (x > 0) {\n  print(x);\nelse {\n  print(0);\n}\n")).parse(partial=True)
    assert any(isinstance(item, ErrorNode) for item in partial.statements[1].body)


def test_stage1_intent_guard_protects_branches():
    base = parse("int x = 1; if (x > 0) { print(1); } else if (x < 0) { print(2); } else { print(3); }")
    moved = parse("int x = 1; if (x > 0) { print(1); print(2); } else if (x < 0) { } else { print(3); }")
    dropped = parse("int x = 1; if (x > 0) { print(1); } else if (x < 0) { print(2); }")
    nested = parse("int x = 1; if (x > 0) { if (x < 0) { print(1); } else { print(2); } }")
    rebound = parse("int x = 1; if (x > 0) { if (x < 0) { print(1); } } else { print(2); }")
    assert "CONTROL_FLOW_CHANGED" in compare(fingerprint(base), fingerprint(moved))
    assert "CONTROL_FLOW_CHANGED" in compare(fingerprint(base), fingerprint(dropped))
    assert "CONTROL_FLOW_CHANGED" in compare(fingerprint(nested), fingerprint(rebound))
    assert compare(fingerprint(base), fingerprint(parse(pretty_print(base)))) == []


def test_stage1_intent_guard_logic_and_modulo():
    base = parse("int x = 4; bool b = x > 1 && x < 9; int r = x % 3; if (b && x > 2) { print(r); }")
    swapped = parse("int x = 4; bool b = x > 1 || x < 9; int r = x / 3; if (b || x > 2) { print(r); }")
    violations = compare(fingerprint(base), fingerprint(swapped))
    assert "DEPENDENCY_CHANGED" in violations and "CONDITION_INVERTED" in violations


def test_stage1_patch_else_branch_and_unary():
    ast = parse("int x = 1; if (x > 0) { print(x); } else { print(0); }")
    if_node = ast.statements[1]
    inserted = apply_edits(ast, [{"op": "INSERT_STMT", "parent": if_node.node_id, "index": 0, "branch": "else", "node": {"type": "PrintStmt", "expr": {"type": "UnaryOp", "op": "-", "operand": {"type": "Identifier", "name": "x"}}}}])
    assert "} else {\n  print((-x));\n  print(0);\n}" in pretty_print(inserted)
    else_print = if_node.else_body[0]
    removed = apply_edits(ast, [{"op": "DELETE_NODE", "target": else_print.node_id}])
    assert removed.statements[1].else_body == []
    with pytest.raises(PatchError):
        apply_edits(ast, [{"op": "REPLACE_NODE", "target": else_print.node_id, "node": {"type": "UnaryOp", "op": "~", "operand": {"type": "Number", "value": "1"}}}])
    built = apply_edits(ast, [{"op": "REPLACE_NODE", "target": if_node.node_id, "node": {"type": "IfStmt", "condition": {"type": "BoolLit", "value": True}, "body": [], "else_body": {"type": "IfStmt", "condition": {"type": "BoolLit", "value": False}, "body": []}}}])
    assert "} else if (false) {" in pretty_print(built)


def test_array_declaration_and_indexing():
    src = "int[] arr = [10, 20, 30]; int first = arr[0]; print(first);"
    ok, err, err_type = verify_fix(src)
    assert ok, f"Expected verify_fix to pass, got: {err_type} - {err}"
    ast = parse(src)
    assert isinstance(ast.statements[0].expr, ArrayLit)
    assert isinstance(ast.statements[1].expr, IndexExpr)
    assert pretty_print(ast) == "int[] arr = [10, 20, 30];\nint first = arr[0];\nprint(first);"


def test_array_mutation_and_empty_literal():
    src = "string[] names = [\"alice\", \"bob\"]; names[1] = \"charlie\"; bool[] flags = [];"
    ok, err, err_type = verify_fix(src)
    assert ok, f"Expected verify_fix to pass, got: {err_type} - {err}"
    ast = parse(src)
    assert isinstance(ast.statements[1], ArrayAssignment)
    assert pretty_print(ast) == "string[] names = [\"alice\", \"bob\"];\nnames[1] = \"charlie\";\nbool[] flags = [];"


def test_array_semantic_type_errors():
    with pytest.raises(SemanticError) as exc1:
        SemanticAnalyzer().analyze(parse("int x = 5; int y = x[0];"))
    assert "cannot index non-array type" in str(exc1.value)

    with pytest.raises(SemanticError) as exc2:
        SemanticAnalyzer().analyze(parse("int[] a = [1, 2]; int y = a[true];"))
    assert "array index must be int" in str(exc2.value)

    with pytest.raises(SemanticError) as exc3:
        SemanticAnalyzer().analyze(parse("int[] a = [1, \"text\"];"))
    assert "inconsistent array element types" in str(exc3.value)

    with pytest.raises(SemanticError) as exc4:
        SemanticAnalyzer().analyze(parse("int[] a = [1, 2]; a[0] = false;"))
    assert "cannot assign bool to array of int" in str(exc4.value)


def test_array_ast_patch_and_intent():
    ast = parse("int[] a = [1, 2]; a[0] = 3;")
    nodes = index_nodes(ast)
    idx_assign = ast.statements[1]
    patched = apply_edits(ast, [{
        "op": "REPLACE_NODE",
        "target": idx_assign.node_id,
        "node": {
            "type": "ArrayAssignment",
            "name": "a",
            "index": {"type": "Number", "value": "1"},
            "expr": {"type": "Number", "value": "99"}
        }
    }])
    assert "a[1] = 99;" in pretty_print(patched)
    fp_orig = fingerprint(ast)
    fp_repaired = fingerprint(parse(pretty_print(ast)))
    assert compare(fp_orig, fp_repaired) == []


def test_function_definition_and_calls():
    src = """int add(int a, int b) {
  return (a + b);
}
int res = add(10, 20);
print(res);
"""
    ok, err, err_type = verify_fix(src)
    assert ok, f"Expected verify_fix to pass, got {err_type}: {err}"
    ast = parse(src)
    assert pretty_print(ast).strip() == src.strip()


def test_function_void_and_return():
    src = """void logMessage(string msg) {
  print(msg);
  return;
}
logMessage("status ok");
"""
    ok, err, err_type = verify_fix(src)
    assert ok, f"Expected verify_fix to pass, got {err_type}: {err}"
    ast = parse(src)
    assert pretty_print(ast).strip() == src.strip()


def test_function_semantic_errors():
    with pytest.raises(SemanticError) as exc1:
        SemanticAnalyzer().analyze(parse("int foo(int a, int a) { return a; }"))
    assert "duplicate parameter" in str(exc1.value)

    with pytest.raises(SemanticError) as exc2:
        SemanticAnalyzer().analyze(parse("int foo() { return \"wrong\"; }"))
    assert "expects return type int, got string" in str(exc2.value)

    with pytest.raises(SemanticError) as exc3:
        SemanticAnalyzer().analyze(parse("void bar() { return 42; }"))
    assert "void function 'bar' cannot return a value" in str(exc3.value)

    with pytest.raises(SemanticError) as exc4:
        SemanticAnalyzer().analyze(parse("return 1;"))
    assert "return statement outside function" in str(exc4.value)

    with pytest.raises(SemanticError) as exc5:
        SemanticAnalyzer().analyze(parse("int f(int x) { return x; } int y = f(1, 2);"))
    assert "expects 1 arguments, got 2" in str(exc5.value)

    with pytest.raises(SemanticError) as exc6:
        SemanticAnalyzer().analyze(parse("int f(int x) { return x; } int y = f(\"hello\");"))
    assert "argument type mismatch" in str(exc6.value)

    with pytest.raises(SemanticError) as exc7:
        SemanticAnalyzer().analyze(parse("void v() {} int x = v();"))
    assert "cannot use void function" in str(exc7.value)


def test_function_ast_patch_and_intent():
    ast = parse("int doubleIt(int x) { return (x + x); } int r = doubleIt(5);")
    fn_node = ast.statements[0]
    patched = apply_edits(ast, [{
        "op": "REPLACE_NODE",
        "target": fn_node.node_id,
        "node": {
            "type": "FunctionDef",
            "return_type": "int",
            "name": "doubleIt",
            "params": [{"type": "Param", "var_type": "int", "name": "x"}],
            "body": [{"type": "ReturnStmt", "expr": {"type": "BinaryOp", "op": "*", "left": {"type": "Identifier", "name": "x"}, "right": {"type": "Number", "value": "2"}}}]
        }
    }])
    assert "return (x * 2);" in pretty_print(patched)
    fp_orig = fingerprint(ast)
    fp_repaired = fingerprint(parse(pretty_print(ast)))
    assert compare(fp_orig, fp_repaired) == []
