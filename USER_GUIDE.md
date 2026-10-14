# Beginner's Guide: AI-Assisted Compiler Frontend

This project checks programs written in a tiny programming language. If it finds an error, it can ask your local Qwen AI model to suggest a repair, then verifies that the repair is correct before accepting it.

It has two special features:

1. **AST node-targeted structural patching**: the AI can propose small edits to the internal program tree instead of rewriting the entire source file.
2. **Semantic intent-invariance guard**: the compiler rejects a repair that changes unrelated program logic, such as reversing a loop condition just to remove an error.

## 1. Start the Project

Open PowerShell and move into the project folder:

```powershell
cd D:\Complier\compiler-design-project-main
```

Check that Ollama and the required Qwen model are available:

```powershell
ollama list
```

You should see this model:

```text
qwen2.5-coder:7b
```

If it is missing, download it once:

```powershell
ollama pull qwen2.5-coder:7b
```

## 2. The One Command to Remember

To check and repair a file, use:

```powershell
python main.py myprogram.lang --repair-mode text --intent-guard on
```

For a beginner, this is the recommended command:

- `text` asks AI for a complete corrected program.
- `on` protects the logic that is unrelated to the reported error.

## 3. Write Your First Valid Program

Create a file named `myprogram.lang` in the project folder. Put this code inside it:

```text
int x = 5;
int y = 10;
print(x + y);
```

Run it:

```powershell
python main.py myprogram.lang
```

Expected result:

```text
[OK] Compiled successfully. No errors detected.
```

The project validates the code; it does not execute `print` or display `15`.

## 4. Language Examples

Every statement ends with a semicolon (`;`).

### Integer, float, boolean, and string variables

```text
int count = 3;
float price = 19.5;
bool active = true;
string name = "Arjun";
print(name);
```

### Arithmetic

```text
int x = 10;
int y = 4;
int total = x + y * 2;
print(total);
```

### Comparisons

```text
int score = 80;
bool passed = score > 40;
print(passed);
```

Supported comparison operators are:

```text
==   !=   <   >
```

### If statement

```text
int age = 18;
if (age > 17) {
  print("adult");
}
```

The condition inside `if (...)` must be a boolean expression.

### While loop

```text
int i = 0;
while (i < 3) {
  print(i);
  i = i + 1;
}
```

### Type casts

Use function-style casts:

```text
int x = 5;
float y = float(x);
bool enabled = bool(x);
print(y);
```

Use `float(x)`, `int(x)`, or `bool(x)`. Do not use C-style casts such as `(float)x`.

## 5. Examples of Errors the Project Can Repair

### Missing semicolon: syntax error

```text
int x = 5
```

Run:

```powershell
python main.py tests\tc07.lang --repair-mode text --intent-guard on
```

The AI may add the missing `;`, and the compiler verifies the result.

### Wrong type: semantic error

```text
int x = "hello";
```

Run:

```powershell
python main.py tests\tc17.lang --repair-mode text --intent-guard on
```

The compiler reports that a string cannot be assigned to an integer.

### Undeclared variable: semantic error

```text
x = 5;
```

Try:

```powershell
python main.py tests\tc15.lang --repair-mode text --intent-guard on
```

### Illegal character: lexical error

```text
int x = 5 @ 3;
```

Try:

```powershell
python main.py tests\tc01.lang --repair-mode text --intent-guard on
```

### Unterminated string: lexical error

```text
string name = "Arjun;
```

Try:

```powershell
python main.py tests\tc05.lang --repair-mode text --intent-guard on
```

## 6. Repair Modes

### Text mode: recommended for normal use

```powershell
python main.py tests\tc17.lang --repair-mode text --intent-guard on
```

The AI returns complete fixed source code. This is the simplest mode and is generally the most forgiving.

### AST mode: structural repair

```powershell
python main.py tests\tc17.lang --repair-mode ast --intent-guard on
```

AST means Abstract Syntax Tree, which is the structured representation of your program. In this mode, the AI must provide a small, validated edit such as replacing one incorrect expression or inserting a statement. The compiler then turns the edited tree back into source code and verifies it.

Use AST mode when you want the repair to be limited to a small structural change. If the error is lexical, or a partial program tree cannot be built, it automatically uses text fallback mode.

If AST mode reports errors such as `SCHEMA: unknown node type`, the AI did not return the required edit format. Retry with text mode:

```powershell
python main.py tests\tc17.lang --repair-mode text --intent-guard on
```

## 7. Intent Guard

Keep the guard on in almost every case:

```powershell
python main.py myprogram.lang --repair-mode text --intent-guard on
```

For example, imagine this loop:

```text
while (i < n) {
  i = i + 1;
}
```

An unsafe repair could change `i < n` into `i > n`; that may compile but completely changes what the program does. The intent guard compares the original and repaired program outside the error location and rejects changes such as:

- changed `if` or `while` control flow
- reversed or replaced comparisons
- removed assignments or statements
- changed variable dependencies
- changed printed expressions

You can disable it only for experimentation:

```powershell
python main.py myprogram.lang --repair-mode text --intent-guard off
```

## 8. Interactive Mode

Start interactive mode:

```powershell
python main.py --interactive --repair-mode text --intent-guard on
```

Enter language code, then press Enter on a blank line to submit it:

```text
> int x = 5;
... print(x);
...
```

Important: interactive mode accepts only the tiny language. Do not type PowerShell commands such as `python evaluate.py` at the `>` or `...` prompt.

To leave interactive mode, type:

```text
quit
```

Then run PowerShell commands only after you return to a prompt that starts with `PS`.

## 9. Sample Test Files

The `tests` folder contains intentionally broken source files:

| Category | Files | Example |
| --- | --- | --- |
| Lexical errors | `tc01` to `tc06` | illegal character, malformed number, unterminated string |
| Syntax errors | `tc07` to `tc14` | missing semicolon, missing parenthesis, invalid expression |
| Semantic errors | `tc15` to `tc20` | undeclared variable, redeclaration, type mismatch |
| Intent-drift cases | `tc21` to `tc26` | errors inside conditions and loop logic |

Run any one file like this:

```powershell
python main.py tests\tc21.lang --repair-mode text --intent-guard on
```

## 10. Run the Offline Tests

These tests do not call Ollama. They check the parser, AST IDs, partial ASTs, edit validation, unparser, intent guard, and fallback behavior:

```powershell
python -m pytest -q
```

Expected result:

```text
6 passed
```

## 11. Run the Full Evaluation

This runs all sample programs in four configurations:

1. Text repair with guard off
2. Text repair with guard on
3. AST repair with guard off
4. AST repair with guard on

Run it from PowerShell:

```powershell
python evaluate.py
```

It can take time because it calls the local Qwen model for many repairs. The final measurements are saved in `results.json`.

## 12. Understand the Result

For a successful repair, you will see something like:

```text
Original error [SEMANTIC]: cannot assign string to int
Repair attempts:
  Attempt 1: PASS
[OK] Fixed in 1 attempt(s).
Fixed code:
int x = 1;
```

For an unsuccessful repair, you may see:

```text
[FAIL] Could not produce a verified fix after 3 attempts.
```

That does not mean the compiler is broken. It means the AI suggestions either did not compile, failed validation, did not preserve intent, or in AST mode did not follow the required structural-edit format.

## 13. Troubleshooting

### `File not found`

Make sure you are in the project directory:

```powershell
cd D:\Complier\compiler-design-project-main
```

### `ollama` is not recognized

Install Ollama, restart PowerShell, then run `ollama list` again.

### The model is missing

```powershell
ollama pull qwen2.5-coder:7b
```

### AST mode fails with `SCHEMA`

Use text mode:

```powershell
python main.py yourfile.lang --repair-mode text --intent-guard on
```

### Commands appear after `>` or `...`

You are inside interactive mode. Type `quit`, then run your command at the normal `PS ...>` prompt.

## Quick Reference

```powershell
cd D:\Complier\compiler-design-project-main
ollama list
python main.py myprogram.lang --repair-mode text --intent-guard on
python main.py --interactive --repair-mode text --intent-guard on
python -m pytest -q
python evaluate.py
```
