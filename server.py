import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ast_nodes import ArrayAssignment, Declaration, ErrorNode, FunctionDef, Program, child_nodes, index_nodes
from errors import build_error_record
from lexer import LexError, lex
from parser import ParseError, Parser
from repair_loop import self_healing_repair
from semantic import SemanticAnalyzer, SemanticError
from unparser import pretty_print

ROOT = Path(__file__).parent
TESTS = ROOT / "tests"
WEB = ROOT / "web"

app = FastAPI(title="LangFix")


class CompileRequest(BaseModel):
    source: str


class RepairRequest(BaseModel):
    source: str
    repair_mode: str = "ast"
    intent_guard: bool = True
    model: str | None = None


def _label(node):
    if isinstance(node, ErrorNode):
        return f"expected {node.expected}, found {node.found}"
    if isinstance(node, Program):
        return f"{len(node.statements)} statements"
    try:
        text = pretty_print(node)
    except TypeError:
        return ""
    first = text.splitlines()[0] if text else ""
    return first if len(first) <= 60 else first[:57] + "..."


def _node_json(node, role):
    return {"id": node.node_id, "type": type(node).__name__, "label": _label(node), "line": node.line, "col": getattr(node, "col", 0), "role": role}


def _context(ast, target_id):
    if ast is None or target_id is None:
        return None
    nodes = index_nodes(ast)
    target = nodes.get(target_id)
    if target is None:
        return None
    ancestors = []
    parent = nodes.get(target.parent_id)
    while parent is not None:
        ancestors.append(_node_json(parent, "ancestor"))
        parent = nodes.get(parent.parent_id)
    direct = nodes.get(target.parent_id)
    siblings = [_node_json(item, "sibling") for item in child_nodes(direct)] if direct else []
    children = [_node_json(item, "child") for item in child_nodes(target)]
    depth = 0

    def measure(node, level):
        nonlocal depth
        depth = max(depth, level)
        for child in child_nodes(node):
            measure(child, level + 1)

    measure(ast, 1)
    return {"target": _node_json(target, "target"), "ancestors": list(reversed(ancestors)), "siblings": siblings, "children": children, "depth": depth, "node_count": len(nodes)}


def _symbols(ast, table, analyzer=None, checked=True):
    lines, values, types = {}, {}, {}
    if ast is not None:
        for node in index_nodes(ast).values():
            if isinstance(node, Declaration) and node.name not in lines:
                lines[node.name] = node.line
                values[node.name] = _label(node.expr)
                types[node.name] = node.var_type
            elif isinstance(node, FunctionDef) and node.name not in lines:
                lines[node.name] = node.line
                params_str = ", ".join(f"{p.var_type} {p.name}" for p in node.params)
                values[node.name] = f"({params_str})"
                types[node.name] = f"{node.return_type}()"
    if checked:
        res = [{"name": name, "type": kind, "line": lines.get(name), "scope": "global", "value": values.get(name, ""), "status": "resolved"} for name, kind in table.items()]
        if analyzer is not None:
            for fname, finfo in getattr(analyzer, "functions", {}).items():
                if not any(item["name"] == fname for item in res):
                    params_str = ", ".join(f"{t} {n}" for t, n in finfo["params"])
                    res.append({"name": fname, "type": f"{finfo['return_type']}()", "line": lines.get(fname), "scope": "global", "value": f"({params_str})", "status": "resolved"})
        return res
    return [{"name": name, "type": types[name], "line": lines[name], "scope": "global", "value": values[name], "status": "parsed"} for name in lines]


def _target_id(ast, line):
    if ast is None:
        return None
    nodes = [node for node in index_nodes(ast).values() if node.line == line and not isinstance(node, Program)]
    return nodes[0].node_id if nodes else None


def _diagnose(source):
    analyzer = SemanticAnalyzer()
    ast = None
    started = time.perf_counter()
    try:
        ast = Parser(lex(source)).parse()
        analyzer.analyze(ast)
        return None, ast, analyzer, (time.perf_counter() - started) * 1000
    except (LexError, ParseError, SemanticError) as error:
        record = build_error_record(error, source, dict(analyzer.symbol_table))
        if isinstance(error, ParseError):
            try:
                ast = Parser(lex(source)).parse(partial=True)
            except LexError:
                ast = None
        record.ast = ast
        record.target_node_id = _target_id(ast, error.line)
        return record, ast, analyzer, (time.perf_counter() - started) * 1000


def _record_json(record, ast, analyzer):
    return {
        "error_type": record.error_type,
        "message": record.message,
        "line": record.line,
        "column": record.column,
        "source_line": record.source_line,
        "grammar_rule": record.grammar_rule,
        "target_node_id": record.target_node_id,
        "symbols": _symbols(ast, record.symbol_table, analyzer, record.error_type == "SEMANTIC"),
        "ast_context": _context(ast, record.target_node_id),
    }


@app.post("/api/compile")
def compile_endpoint(request: CompileRequest):
    record, ast, analyzer, elapsed = _diagnose(request.source)
    if record is None:
        return {"status": "ok", "elapsed_ms": elapsed, "symbols": _symbols(ast, analyzer.symbol_table, analyzer), "node_count": len(index_nodes(ast))}
    return {"status": "error", "elapsed_ms": elapsed, "error": _record_json(record, ast, analyzer)}


@app.post("/api/repair")
def repair_endpoint(request: RepairRequest):
    if request.repair_mode not in {"ast", "text"}:
        raise HTTPException(400, "repair_mode must be ast or text")
    record, ast, analyzer, _ = _diagnose(request.source)
    if record is None:
        return {"status": "ok"}
    started = time.time()
    try:
        result = self_healing_repair(request.source, record, max_attempts=3, repair_mode=request.repair_mode, intent_guard=request.intent_guard, original_ast=ast, model=request.model or None)
    except Exception as error:
        raise HTTPException(503, f"LLM unavailable: {error}")
    return {
        "status": "fixed" if result.success else "failed",
        "elapsed": time.time() - started,
        "repair_mode": result.repair_mode,
        "fixed_code": result.final_fixed_code,
        "explanation": result.final_explanation,
        "total_attempts": result.total_attempts,
        "attempts": [
            {
                "number": attempt.attempt_num,
                "passed": attempt.verify_passed,
                "code": attempt.llm_fixed_code,
                "explanation": attempt.llm_explanation,
                "error": attempt.verify_error,
                "error_type": attempt.verify_error_type,
                "reason": attempt.rejected_reason,
                "violations": attempt.intent_violations,
                "edits": attempt.edits_applied,
            }
            for attempt in result.attempts
        ],
        "error": _record_json(record, ast, analyzer),
    }


@app.post("/api/format")
def format_endpoint(request: CompileRequest):
    try:
        return {"source": pretty_print(Parser(lex(request.source)).parse()) + "\n"}
    except (LexError, ParseError) as error:
        raise HTTPException(422, f"cannot format: {error.message}")


@app.get("/api/examples")
def examples():
    expected = json.loads((TESTS / "expected.json").read_text(encoding="utf-8"))
    items = [{"name": name, "category": meta["category"], "source": (TESTS / name).read_text(encoding="utf-8")} for name, meta in sorted(expected.items())]
    items += [{"name": f"ok/{path.name}", "category": "valid", "source": path.read_text(encoding="utf-8")} for path in sorted((TESTS / "ok").glob("*.lang"))]
    return items


@app.get("/api/health")
def health():
    try:
        import ollama
        response = ollama.list()
        items = getattr(response, "models", None)
        if items is None:
            items = response.get("models", [])
        models = [getattr(item, "model", None) or (item.get("model") or item.get("name") if isinstance(item, dict) else None) for item in items]
        return {"ollama": True, "models": [name for name in models if name]}
    except Exception:
        return {"ollama": False, "models": []}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
