from ast_nodes import ErrorNode, index_nodes
from ast_patch import PatchError, apply_edits
from intent import IntentFingerprint, compare, fingerprint
from lexer import lex
from parser import Parser
from unparser import pretty_print


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
