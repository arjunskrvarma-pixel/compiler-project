from pathlib import Path
from main import compile_source

def run(label, code):
    print("\n" + "=" * 60)
    print(f"TEST: {label}")
    print("=" * 60)
    print("Input:")
    print(code)

    Path("tmp.lang").write_text(code, encoding="utf-8")

    outcome = compile_source(code)

    if outcome["status"] == "ok":
        print("\n[OK] Compiled successfully. No errors detected.")
        return

    record = outcome["original_error"]
    print(f"\nOriginal error [{record.error_type}]: {record.message}")
    print(f"  Line {record.line}, Column {record.column}")

    result = outcome["result"]
    print("\nRepair attempts:")
    for a in result.attempts:
        if a.verify_passed:
            print(f"  Attempt {a.attempt_num}: PASS")
        else:
            print(f"  Attempt {a.attempt_num}: FAIL "
                  f"({a.verify_error_type}: {a.verify_error})")

    if outcome["status"] == "fixed":
        print(f"\n[OK] Fixed in {result.total_attempts} attempt(s).")
        print(f"Explanation: {result.final_explanation}")
        print("\nFixed code:")
        print(result.final_fixed_code)
    else:
        print(f"\n[FAIL] Could not fix after {result.total_attempts} attempts.")


if __name__ == "__main__":
    run("Valid code", "int x = 5;")
    run("Missing semicolon", "int x = 5")
    run("Redeclared variable", "int x = 5;\nint x = 10;")
    run("Type mismatch", "int x = 5;\nfloat y = 2.5;\nx = y + 1;")
