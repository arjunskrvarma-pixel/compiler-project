# AI-Assisted Compiler Frontend

This project validates a small statically typed language and uses a local Ollama model only as an untrusted repair-suggestion engine. Every candidate repair is verified again by the deterministic compiler before it is accepted.

## Features

- Lexer, recursive-descent parser, AST, and semantic type checker
- Structured lexical, syntax, and semantic error records with the active symbol table
- Local Ollama integration using `qwen2.5-coder:3b`
- Text repair mode with compiler-feedback retries
- AST node-targeted structural patching with stable pre-order node IDs, partial ASTs, compact context export, and a strict edit DSL
- Semantic intent-invariance guard that rejects repairs which alter protected control-flow, assignments, dependencies, or printed expressions outside the error region
- Deterministic verification of every candidate repair
- Four-configuration benchmark output: text/AST repair with intent guard on/off

## Requirements

- Python 3.10+
- Ollama installed and running
- The `qwen2.5-coder:3b` model
- Pytest for the offline test suite

```bash
ollama pull qwen2.5-coder:3b
python -m pip install pytest
```

## Usage

```bash
python main.py tests/tc01.lang
python main.py tests/tc01.lang --repair-mode ast --intent-guard on
python main.py tests/tc01.lang --repair-mode text --intent-guard off
python main.py --interactive --repair-mode ast --intent-guard on
python evaluate.py
python evaluate.py --model qwen2.5-coder:3b
python -m pytest tests -q
```

`--repair-mode ast` is the default. AST mode falls back automatically to text mode for lexical errors or when no partial AST can be produced. `--intent-guard on` is the default.

## Project Structure

- `lexer.py`: tokenization and lexical errors
- `parser.py`: parsing, partial AST recovery, node metadata assignment
- `ast_nodes.py`: AST dataclasses, `ErrorNode`, node indexing
- `unparser.py`: canonical AST-to-source rendering
- `semantic.py`: symbol table and type checks
- `errors.py`: structured error records
- `ast_context.py`: compact target/ancestor/sibling context for structural repair
- `ast_patch.py`: strict AST edit schema validation and application
- `intent.py`: intent fingerprints and violation comparison
- `llm.py`: the only Ollama client module
- `repair_loop.py`: text and AST repair orchestration
- `verifier.py`: deterministic trust boundary
- `evaluate.py`: four-configuration benchmark runner
- `tests/`: 26 repair fixtures and offline feature tests

## Known Limitations

- This is a compiler frontend: it does not execute code or generate a backend target.
- The semantic analyzer currently uses one symbol table, so block-local scope is not modeled.
- Intent comparison protects the represented AST semantics; it cannot infer programmer intent absent from source.
- Repair quality still depends on the local model, but model output is never accepted without schema and compiler verification.

## Web Frontend (LangFix IDE)

```bash
python -m pip install fastapi uvicorn
python server.py
```

Open http://127.0.0.1:8000. The left panel is the editor (live diagnostics, error squiggle, inline tooltip); the right panel has Errors (error card, symbol table, AST context), Repair Attempts (timeline with intent/schema rejections) and Corrected Code (verified fix, diff view, apply/copy/download). The top bar selects AST/Text repair, the intent guard and the Ollama model. API: `POST /api/compile`, `POST /api/repair`, `POST /api/format`, `GET /api/examples`, `GET /api/health`. Files: `server.py`, `web/`.
