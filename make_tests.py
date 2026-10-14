"""Generates tests/*.lang and tests/expected.json."""
import json
from pathlib import Path

TESTS = [
    # --- LEXICAL (6) ---
    ("tc01", "lexical",  "int x = 5 @ 3;"),
    ("tc02", "lexical",  'print("hello);'),
    ("tc03", "lexical",  "int x = 12abc;"),
    ("tc04", "lexical",  "int x = 5; float y = 2.5$;"),
    ("tc05", "lexical",  'string s = "unterminated'),
    ("tc06", "lexical",  "bool b = true; int # = 5;"),

    # --- SYNTAX (8) ---
    ("tc07", "syntax",   "int x = 5"),
    ("tc08", "syntax",   "if (x > 5 { print(x); }"),
    ("tc09", "syntax",   "int x = 5 + ;"),
    ("tc10", "syntax",   "int = 5;"),
    ("tc11", "syntax",   "while (true) { print(1); "),
    ("tc12", "syntax",   "print(5)"),
    ("tc13", "syntax",   "int x = (5 + 3;"),
    ("tc14", "syntax",   "if x > 5 { print(x); }"),

    # --- SEMANTIC (6) ---
    ("tc15", "semantic", "x = 5;"),
    ("tc16", "semantic", "int x = 5;\nint x = 10;"),
    ("tc17", "semantic", 'int x = "hello";'),
    ("tc18", "semantic", "int x = 5;\nfloat y = 2.5;\nx = y + 1;"),
    ("tc19", "semantic", "if (5) { print(1); }"),
    ("tc20", "semantic", "int y = x + 1;"),
    ("tc21", "semantic", "int i = 0; while (i < true) { i = i + 1; }"),
    ("tc22", "syntax", "bool ok = 1 < 2 print(ok);"),
    ("tc23", "semantic", "if (1) { print(1); }"),
    ("tc24", "semantic", "int n = 3; while (i < n) { print(n); }"),
    ("tc25", "semantic", "int x = 0; if (x < 3) { bool b = 1; }"),
    ("tc26", "syntax", "int x = 1; while (x < 3) { print(x) x = x + 1; }"),
]


def main():
    out_dir = Path("tests")
    out_dir.mkdir(exist_ok=True)

    expected = {}
    for name, category, code in TESTS:
        (out_dir / f"{name}.lang").write_text(code, encoding="utf-8")
        expected[f"{name}.lang"] = {"category": category, "should_fix": True}

    (out_dir / "expected.json").write_text(
        json.dumps(expected, indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(TESTS)} test files + expected.json to tests/")


if __name__ == "__main__":
    main()
