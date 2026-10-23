import json
import re

import ollama
from errors import ErrorRecord

_MODEL = "qwen2.5-coder:3b"
LANGUAGE_SUMMARY = """LANGUAGE GRAMMAR:
  statement  -> type ID "=" expr ";" | type ID "(" params? ")" block | ID "=" expr ";" | ID "[" expr "]" "=" expr ";" | ID "(" args? ")" ";" | return | if | while | print
  return     -> "return" expr? ";"
  if         -> "if" "(" expr ")" block ( "else" ( if | block ) )?
  while      -> "while" "(" expr ")" block
  print      -> "print" "(" expr ")" ";"
  block      -> "{" statement* "}"
  expr precedence (low to high): || , && , == != , < > <= >= , + - , * / % , unary - ! , postfix [] , primary
  primary    -> NUMBER | STRING | true | false | ID | ID "(" args? ")" | "[" (expr ("," expr)*)? "]" | "(" expr ")" | type "(" expr ")"
  types: int, float, bool, string, void, int[], float[], bool[], string[]. Casts use function syntax int(x), float(x), bool(x), never C-style.
TYPE RULES: functions define return type (or void); return expr must match function return type; array index must be int; array element types must be homogeneous; && || ! need bool; % needs int and int; unary - needs int or float; < > <= >= need two identical numeric types; == != need identical types; conditions must be bool; no implicit conversion on assignment."""
_FALLBACK = {"explanation": "LLM returned invalid format", "fixed_code": ""}


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def call_llm_prompt(prompt: str, required_fields: tuple[str, ...], fallback: dict, validator=None, model: str | None = None) -> dict:
    messages = [{"role": "user", "content": prompt}]
    for retry in range(2):
        response = ollama.chat(
            model=model or _MODEL, messages=messages, options={"temperature": 0.1}
        )
        text = response["message"]["content"]
        try:
            data = json.loads(_strip_fences(text))
        except json.JSONDecodeError:
            data = None
        valid = validator(data) if validator else isinstance(data, dict) and all(isinstance(data.get(key), str) for key in required_fields)
        if valid:
            return data
        if retry == 0:
            messages.extend([
                {"role": "assistant", "content": text},
                {"role": "user", "content": "Return ONLY valid JSON in the requested format."},
            ])
    return fallback


def call_llm(error_record: ErrorRecord) -> dict:
    prompt = f"""You are a compiler error correction assistant.
A programmer wrote code in a small statically-typed language.
{LANGUAGE_SUMMARY}

ERROR TYPE: {error_record.error_type}
ERROR MESSAGE: {error_record.message}
LINE: {error_record.line}, COLUMN: {error_record.column}

BROKEN CODE:
{error_record.context}

VARIABLES IN SCOPE:
{error_record.symbol_table}

The numbered lines in BROKEN CODE are for reference only.
Do NOT include the line numbers or the '|' character in your fixed_code.

Respond ONLY in this exact JSON format, no extra text:
{{"explanation": "...", "fixed_code": "..."}}

"""
    return call_llm_prompt(prompt, ("explanation", "fixed_code"), _FALLBACK)
