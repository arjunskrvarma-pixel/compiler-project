const $ = (id) => document.getElementById(id);
const LINE = 24;
const PAD = 8;
const LEFT_PAD = 12;

const DEFAULT_SOURCE = `int x = 5;
if (x > 5 {
  print(x);
}
int counter = 0;
while (counter < 3) {
  print(counter);
  counter = counter + 1;
}
`;

const TOKEN_SYMBOLS = {
  RPAREN: ")", LPAREN: "(", RBRACE: "}", LBRACE: "{", SEMI: ";", ASSIGN: "=",
  ID: "identifier", type: "type", expression: "expression", statement: "statement",
};

const PRODUCTIONS = {
  IfStmt: 'if_stmt   ::= "if" "(" expr ")" block ( "else" ( if_stmt | block ) )?',
  WhileStmt: 'while_stmt ::= "while" "(" expr ")" block',
  PrintStmt: 'print_stmt ::= "print" "(" expr ")" ";"',
  Declaration: 'declaration ::= type ID "=" expr ";"',
  Assignment: 'assignment ::= ID "=" expr ";"',
  BinaryOp: "expr ::= or ; or ::= and ( \"||\" and )* ; and ::= equality ( \"&&\" equality )*",
  UnaryOp: 'unary ::= ( "-" | "!" ) unary | primary',
  Program: "program ::= statement*",
  ErrorNode: "statement ::= declaration | assignment | if_stmt | while_stmt | print_stmt",
};

const KEYWORDS = new Set(["if", "else", "while", "print"]);
const TYPES = new Set(["int", "float", "bool", "string"]);
const BOOLS = new Set(["true", "false"]);

const state = {
  source: "",
  original: "",
  fileName: "untitled.lang",
  mode: "ast",
  guard: true,
  model: "",
  diagnosis: null,
  stale: false,
  repair: null,
  repairing: false,
  repairError: "",
  tab: "errors",
  correctedView: "code",
  showTooltip: false,
  examples: [],
  ollama: null,
};

function escapeHtml(text) {
  return text.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function tokenize(line) {
  const re = /("(?:[^"\\]|\\.)*"?)|(\d+(?:\.\d+)?)|([A-Za-z_]\w*)|(&&|\|\||[=!<>]=|[-+*/%<>=!(){};,\[\]])|(\s+)|(.)/g;
  const tokens = [];
  let m;
  while ((m = re.exec(line))) {
    let cls = "";
    if (m[1]) cls = "tk-str";
    else if (m[2]) cls = "tk-num";
    else if (m[3]) cls = KEYWORDS.has(m[3]) ? "tk-kw" : TYPES.has(m[3]) ? "tk-type" : BOOLS.has(m[3]) ? "tk-bool" : "";
    else if (m[4]) cls = "tk-op";
    tokens.push({ text: m[0], start: m.index, cls });
  }
  return tokens;
}

function highlightLine(line, errCol) {
  const tokens = tokenize(line);
  let html = "";
  for (const token of tokens) {
    const hit = errCol !== null && errCol >= token.start && errCol < token.start + token.text.length && token.text.trim();
    const classes = [token.cls, hit ? "squiggle" : ""].filter(Boolean).join(" ");
    html += classes ? `<span class="${classes}">${escapeHtml(token.text)}</span>` : escapeHtml(token.text);
  }
  if (errCol !== null && errCol >= line.length) html += '<span class="eof-marker"></span>';
  return html;
}

function highlightSource(source) {
  return source.split("\n").map((line) => highlightLine(line, null)).join("\n");
}

function currentError() {
  return state.diagnosis && state.diagnosis.status === "error" && !state.stale ? state.diagnosis.error : null;
}

function errorColumn(err, lineText) {
  if (!err) return null;
  if (err.column > 0) return err.column - 1;
  const first = lineText.search(/\S/);
  return first < 0 ? 0 : first;
}

function renderEditor() {
  const lines = state.source.split("\n");
  const err = currentError();
  $("highlight").innerHTML = lines.map((line, index) => {
    const isErr = err && err.line === index + 1;
    const html = highlightLine(line, isErr ? errorColumn(err, line) : null);
    return isErr ? `<span class="line-err">${html || " "}</span>` : html;
  }).join("\n") + "\n";
  $("gutter").innerHTML = lines.map((_, index) => `<div class="${err && err.line === index + 1 ? "err" : ""}">${index + 1}</div>`).join("");
  const pre = $("highlight");
  const editor = $("editor");
  const height = lines.length * LINE + PAD * 2 + LINE;
  pre.style.height = editor.style.height = height + "px";
  $("editorInner").style.height = height + "px";
  const width = Math.max(pre.scrollWidth, pre.parentElement.clientWidth);
  editor.style.width = pre.style.width = width + "px";
  renderTooltip();
}

let charWidth = 7.8;
function measureChar() {
  const probe = document.createElement("span");
  probe.style.cssText = 'font: 13px "JetBrains Mono", monospace; position:absolute; visibility:hidden; white-space:pre';
  probe.textContent = "x".repeat(100);
  document.body.appendChild(probe);
  charWidth = probe.getBoundingClientRect().width / 100 || charWidth;
  probe.remove();
}

function suggestion(err) {
  if (err.error_type === "SYNTAX" && TOKEN_SYMBOLS[err.grammar_rule] && err.grammar_rule.length > 2 && /PAREN|BRACE|SEMI|ASSIGN/.test(err.grammar_rule)) {
    return `Insert <span class="mono text-primary">${escapeHtml(TOKEN_SYMBOLS[err.grammar_rule])}</span> at line ${err.line}, col ${err.column}`;
  }
  if (err.error_type === "LEXICAL") return "Remove or replace the invalid character sequence";
  if (err.error_type === "SEMANTIC") return "Fix the types or declarations so the checker accepts this line";
  return `Provide a valid ${escapeHtml(TOKEN_SYMBOLS[err.grammar_rule] || err.grammar_rule || "construct")} here`;
}

function renderTooltip() {
  const tip = $("tooltip");
  const err = currentError();
  if (!err || !state.showTooltip) { tip.classList.add("hidden"); return; }
  const col = Math.max(0, err.column - 1);
  tip.style.top = PAD + err.line * LINE + 4 + "px";
  tip.style.left = LEFT_PAD + Math.min(col * charWidth, 260) + "px";
  tip.innerHTML = `
    <div class="flex items-start justify-between gap-2 mb-2">
      <div class="flex items-center gap-2 mono text-sm text-error font-semibold"><span class="material-symbols-outlined text-[18px]">cancel</span>[${err.error_type} ERROR]</div>
      <div class="flex items-center gap-2"><span class="mono text-[11px] text-outline">line ${err.line}:${err.column}</span>
      <button data-action="close-tip" class="text-outline hover:text-on-surface"><span class="material-symbols-outlined text-[16px]">close</span></button></div>
    </div>
    <p class="mono text-[13px] mb-3">${escapeHtml(err.message)}</p>
    <div class="rounded bg-surface-container-lowest px-3 py-2 text-[13px] flex items-center gap-2 mb-3"><span class="material-symbols-outlined text-[16px] text-primary">auto_fix_high</span><span>Suggest: ${suggestion(err)}</span></div>
    <div class="flex items-center justify-between">
      <button data-action="goto-errors" class="flex items-center gap-1 text-xs text-on-surface-variant hover:text-on-surface"><span class="material-symbols-outlined text-[15px]">lightbulb</span>Details</button>
      <button data-action="repair" class="btn btn-primary !py-1 text-[13px]" ${repairDisabled()}><span class="material-symbols-outlined text-[16px]">play_arrow</span>Auto-Repair (${state.mode.toUpperCase()})</button>
    </div>`;
  tip.classList.remove("hidden");
}

function repairDisabled() {
  return state.repairing ? "disabled" : "";
}

function chipFor(type) {
  const map = {
    LEXICAL: "bg-warn/20 text-warn", SYNTAX: "bg-error-container/60 text-error", SEMANTIC: "bg-secondary/20 text-secondary",
    INTENT: "bg-primary-container/25 text-primary", SCHEMA: "bg-surface-container-highest text-on-surface-variant",
  };
  return `<span class="chip ${map[type] || map.SCHEMA}">${escapeHtml(type || "ERROR")}</span>`;
}

function snippet(err) {
  const lineText = state.source.split("\n")[err.line - 1] ?? err.source_line ?? "";
  const col = errorColumn(err, lineText);
  const prefix = `${err.line} | `;
  const caret = " ".repeat(prefix.length + col) + "^ " + escapeHtml(err.grammar_rule ? `expected ${TOKEN_SYMBOLS[err.grammar_rule] || err.grammar_rule}` : err.message);
  return `<div class="codebox"><span class="text-outline">// Reproduction snippet</span>\n<span class="text-outline">${prefix}</span>${highlightLine(lineText, col)}\n<span class="text-error">${caret}</span></div>`;
}

function symbolTable(symbols) {
  if (!symbols.length) return '<p class="text-sm text-on-surface-variant px-3 pb-3">No symbols declared before this point.</p>';
  return `<div class="overflow-x-auto"><table class="w-full text-left mono text-[12px]">
    <thead class="text-outline text-[10px] uppercase tracking-wider"><tr class="bg-surface-container-lowest"><th class="px-3 py-2">Identifier</th><th class="px-3">Type</th><th class="px-3">Line</th><th class="px-3">Scope</th><th class="px-3">Initial value</th><th class="px-3 text-right">Status</th></tr></thead>
    <tbody>${symbols.map((s) => `<tr class="border-t border-surface-container"><td class="px-3 py-2">${escapeHtml(s.name)}</td><td class="px-3 text-primary">${s.type}</td><td class="px-3">${s.line ? "Ln " + s.line : "—"}</td><td class="px-3">${s.scope}</td><td class="px-3 text-tertiary">${escapeHtml(s.value || "")}</td><td class="px-3 text-right">${s.status === "parsed" ? '<span class="chip bg-warn/15 text-warn normal-case">Parsed only</span>' : '<span class="chip bg-tertiary/15 text-tertiary normal-case">Resolved</span>'}</td></tr>`).join("")}</tbody>
  </table></div>`;
}

function nodeRow(node, indent, kind) {
  const isError = node.type === "ErrorNode";
  const styles = {
    ancestor: "bg-surface-container-high text-on-surface",
    target: isError ? "border border-dashed border-error text-error bg-error-container/20" : "border border-primary-container text-primary bg-primary-container/10",
    child: "bg-surface-container text-primary",
  };
  const icon = isError ? "error" : kind === "target" ? "my_location" : kind === "ancestor" ? "folder_open" : "subdirectory_arrow_right";
  const tag = kind === "target" ? `<span class="chip ${isError ? "bg-error-container text-error" : "bg-primary-container/30 text-primary"}">${isError ? "Expected here" : "Target"}</span>` : "";
  return `<div class="flex items-center gap-2 py-1" style="padding-left:${indent * 18}px">
    <span class="material-symbols-outlined text-[16px] ${isError ? "text-error" : "text-outline"}">${icon}</span>
    <span class="mono text-[12px] px-2 py-0.5 rounded ${styles[kind]}">[Node #${node.id}: ${node.type}${node.label ? " " + escapeHtml(node.label) : ""}]</span>${tag}
    <span class="mono text-[10px] text-outline">Ln ${node.line}</span></div>`;
}

function astContext(ctx, err) {
  if (!ctx) return '<p class="text-sm text-on-surface-variant px-3 pb-3">No AST is available for this error (lexing failed before parsing).</p>';
  const rows = [];
  ctx.ancestors.forEach((node, i) => rows.push(nodeRow(node, i, "ancestor")));
  rows.push(nodeRow(ctx.target, ctx.ancestors.length, "target"));
  ctx.children.forEach((node) => rows.push(nodeRow(node, ctx.ancestors.length + 1, "child")));
  const siblings = ctx.siblings.filter((node) => node.id !== ctx.target.id);
  const stage = { LEXICAL: "Lexer failed", SYNTAX: "Parser failed", SEMANTIC: "Type check failed" }[err.error_type] || "—";
  return `<div class="px-3 pb-3 space-y-3">
    <div class="rounded bg-surface-container-lowest p-3 overflow-x-auto">${rows.join("")}</div>
    ${siblings.length ? `<div><div class="mono text-[10px] uppercase text-outline mb-1">Siblings</div>${siblings.map((node) => nodeRow(node, 0, "child")).join("")}</div>` : ""}
    <div class="grid grid-cols-3 gap-2 text-center mono text-[11px]">
      <div class="rounded bg-surface-container p-2"><div class="text-outline">Tree depth</div><div>${ctx.depth} levels</div></div>
      <div class="rounded bg-surface-container p-2"><div class="text-outline">Nodes</div><div>${ctx.node_count}</div></div>
      <div class="rounded bg-surface-container p-2"><div class="text-outline">Stage</div><div class="text-warn">${stage}</div></div>
    </div></div>`;
}

function section(title, icon, meta, body, open = true) {
  return `<details class="card" ${open ? "open" : ""}>
    <summary class="flex items-center justify-between px-3 py-3"><div class="flex items-center gap-2"><span class="material-symbols-outlined text-[18px] text-primary">${icon}</span><span class="font-semibold">${title}</span>${meta}</div><span class="material-symbols-outlined chev text-outline transition-transform">expand_more</span></summary>
    ${body}</details>`;
}

function emptyState(icon, title, text, extra = "") {
  return `<div class="h-full min-h-[300px] flex flex-col items-center justify-center text-center gap-3 text-on-surface-variant">
    <span class="material-symbols-outlined text-[48px] text-outline">${icon}</span>
    <div class="font-semibold text-on-surface">${title}</div><p class="text-sm max-w-sm">${text}</p>${extra}</div>`;
}

function productionFor(err) {
  const lineText = state.diagnosisSource?.split("\n")[err.line - 1] ?? err.source_line ?? "";
  const head = lineText.trim().split(/[^A-Za-z_]+/)[0];
  const byKeyword = { if: "IfStmt", else: "IfStmt", while: "WhileStmt", print: "PrintStmt", int: "Declaration", float: "Declaration", bool: "Declaration", string: "Declaration" }[head];
  if (byKeyword) return PRODUCTIONS[byKeyword];
  if (/^[A-Za-z_]\w*\s*=/.test(lineText.trim())) return PRODUCTIONS.Assignment;
  const ctx = err.ast_context;
  return ctx ? PRODUCTIONS[ctx.target.type] : "";
}

function renderErrorsTab() {
  const d = state.diagnosis;
  if (!d) return emptyState("terminal", "Write code and press Compile.", "Diagnostics from the lexer, parser and type checker will appear here.");
  if (d.status === "ok") {
    return `<div class="card p-6 text-center border-tertiary/40"><span class="material-symbols-outlined text-[48px] text-tertiary">check_circle</span>
      <div class="text-lg font-semibold mt-2">Compiled successfully. No errors detected.</div>
      <p class="text-sm text-on-surface-variant mt-1 mono">${d.node_count} AST nodes · ${d.elapsed_ms.toFixed(1)} ms</p></div>
      ${section("Symbol Table", "account_tree", `<span class="mono text-[11px] text-outline">${d.symbols.length} symbols</span>`, symbolTable(d.symbols))}`;
  }
  const err = d.error;
  const stale = state.stale ? '<div class="card px-3 py-2 text-sm text-warn flex items-center gap-2"><span class="material-symbols-outlined text-[18px]">sync_problem</span>Source changed since this diagnosis. Recompile to refresh.</div>' : "";
  const production = productionFor(err);
  return `${stale}
  <div class="card border-l-4 !border-l-error p-4 space-y-3">
    <div class="flex items-center justify-between gap-2 flex-wrap">
      <div class="flex items-center gap-2 mono text-sm">${chipFor(err.error_type)}<span class="font-semibold">Line ${err.line}, Col ${err.column}</span>${err.target_node_id ? `<span class="chip bg-surface-container-highest text-on-surface-variant">Node #${err.target_node_id}</span>` : ""}</div>
      <span class="mono text-[11px] text-outline flex items-center gap-1"><span class="material-symbols-outlined text-[14px]">schedule</span>${d.elapsed_ms.toFixed(1)} ms</span>
    </div>
    <div class="text-lg font-semibold">${escapeHtml(err.message)}</div>
    <p class="text-sm text-on-surface-variant">${suggestion(err)}.</p>
    ${production ? `<div class="rounded bg-surface-container-lowest p-3"><div class="flex justify-between mono text-[10px] uppercase text-outline mb-1"><span>Parser expected production</span><span class="text-primary">Grammar</span></div><div class="mono text-[12.5px] text-primary break-words">${escapeHtml(production)}</div></div>` : ""}
    ${snippet(err)}
    <div class="flex items-center justify-end gap-2 flex-wrap">
      <button data-action="goto-line" class="btn btn-ghost"><span class="material-symbols-outlined text-[16px]">my_location</span>Go to line</button>
      <button data-action="repair" class="btn btn-primary" ${repairDisabled()}><span class="material-symbols-outlined text-[18px]">auto_fix_high</span>${state.repairing ? "Repairing…" : `Run ${state.mode.toUpperCase()} Repair`}</button>
    </div>
  </div>
  ${section("Symbol Table", "account_tree", `<span class="mono text-[11px] text-outline">Scope: global</span><span class="chip bg-surface-container-highest text-on-surface-variant ml-1">${err.symbols.length} symbols</span>`, symbolTable(err.symbols))}
  ${section("AST Context (Target Node)", "lan", err.target_node_id ? `<span class="chip ${err.ast_context?.target?.type === "ErrorNode" ? "bg-error-container text-error" : "bg-primary-container/30 text-primary"} ml-1">${err.ast_context?.target?.type === "ErrorNode" ? "Malformed" : "Target"} Node #${err.target_node_id}</span>` : "", astContext(err.ast_context, err))}`;
}

function attemptCard(attempt) {
  const status = attempt.passed ? '<span class="chip bg-tertiary/20 text-tertiary">Pass</span>' : `<span class="chip bg-error-container/60 text-error">Fail · ${escapeHtml(attempt.reason || attempt.error_type)}</span>`;
  const violations = attempt.violations?.length ? `<div class="flex flex-wrap gap-1">${attempt.violations.map((v) => `<span class="chip bg-primary-container/25 text-primary">${escapeHtml(v)}</span>`).join("")}</div>` : "";
  const edits = attempt.edits?.length ? `<details><summary class="text-xs text-on-surface-variant hover:text-on-surface">${attempt.edits.length} AST edit(s)</summary><div class="codebox mt-1 text-[11px]">${escapeHtml(JSON.stringify(attempt.edits, null, 2))}</div></details>` : "";
  return `<div class="relative pl-8">
    <span class="absolute left-0 top-1 w-6 h-6 rounded-full flex items-center justify-center mono text-[11px] ${attempt.passed ? "bg-tertiary text-surface" : "bg-error-container text-error"}">${attempt.number}</span>
    <div class="card p-3 space-y-2">
      <div class="flex items-center justify-between gap-2"><span class="font-semibold text-sm">Attempt ${attempt.number}</span>${status}</div>
      ${attempt.explanation ? `<p class="text-sm text-on-surface-variant">${escapeHtml(attempt.explanation)}</p>` : ""}
      ${!attempt.passed && attempt.error ? `<div class="mono text-[12px] text-error flex gap-1"><span class="material-symbols-outlined text-[15px]">block</span>${chipFor(attempt.error_type)} ${escapeHtml(attempt.error)}</div>` : ""}
      ${violations}${edits}
      ${attempt.code ? `<details><summary class="text-xs text-on-surface-variant hover:text-on-surface">Candidate code</summary><div class="codebox mt-1">${highlightSource(attempt.code)}</div></details>` : ""}
    </div></div>`;
}

function renderAttemptsTab() {
  if (state.repairing) {
    return `<div class="card p-3 flex items-center gap-2 text-sm"><span class="material-symbols-outlined animate-spin text-primary">progress_activity</span>Asking ${escapeHtml(state.model || "the model")} for a ${state.mode.toUpperCase()} repair. Every candidate is re-verified by the compiler…</div>
      ${[1, 2].map(() => '<div class="pl-8"><div class="card p-3 space-y-2"><div class="shimmer h-4 w-1/3"></div><div class="shimmer h-3 w-full"></div><div class="shimmer h-3 w-2/3"></div></div></div>').join("")}`;
  }
  if (state.repairError) return emptyState("cloud_off", "Repair service unavailable", escapeHtml(state.repairError));
  const r = state.repair;
  if (!r) return emptyState("history", "No repair attempts yet", "Compile a program with an error, then run a repair. Up to 3 attempts are made and each one is verified.", currentError() ? `<button data-action="repair" class="btn btn-primary mt-2"><span class="material-symbols-outlined text-[18px]">auto_fix_high</span>Run ${state.mode.toUpperCase()} Repair</button>` : "");
  const head = `<div class="flex items-center justify-between mono text-[12px] text-on-surface-variant"><span>Mode: ${escapeHtml(r.repair_mode)} · Guard: ${state.guard ? "on" : "off"}</span><span>${r.elapsed.toFixed(1)} s</span></div>`;
  return head + `<div class="space-y-3 relative before:absolute before:left-3 before:top-2 before:bottom-2 before:w-px before:bg-outline-variant">${r.attempts.map(attemptCard).join("")}</div>`;
}

function lineDiff(a, b) {
  const x = a.replace(/\n$/, "").split("\n");
  const y = b.replace(/\n$/, "").split("\n");
  const dp = Array.from({ length: x.length + 1 }, () => new Array(y.length + 1).fill(0));
  for (let i = x.length - 1; i >= 0; i--) for (let j = y.length - 1; j >= 0; j--) dp[i][j] = x[i] === y[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out = [];
  let i = 0, j = 0;
  while (i < x.length || j < y.length) {
    if (i < x.length && j < y.length && x[i] === y[j]) { out.push([" ", x[i]]); i++; j++; }
    else if (i < x.length && (j >= y.length || dp[i + 1][j] >= dp[i][j + 1])) { out.push(["-", x[i]]); i++; }
    else { out.push(["+", y[j]]); j++; }
  }
  return out;
}

function renderCorrectedTab() {
  const r = state.repair;
  if (state.repairing) return renderAttemptsTab();
  if (!r) return emptyState("auto_fix_off", "No corrected code yet", "Run a repair to see the verified fix here.", currentError() ? `<button data-action="repair" class="btn btn-primary mt-2"><span class="material-symbols-outlined text-[18px]">auto_fix_high</span>Run ${state.mode.toUpperCase()} Repair</button>` : "");
  const fixed = r.status === "fixed";
  const banner = fixed
    ? `<div class="card p-4 !border-tertiary/50 bg-tertiary/10 flex items-center gap-3"><span class="material-symbols-outlined text-[28px] text-tertiary">verified</span><div><div class="font-semibold text-tertiary">Fixed in ${r.total_attempts} attempt${r.total_attempts > 1 ? "s" : ""} · ${escapeHtml(r.repair_mode)} mode · ${r.elapsed.toFixed(1)}s</div><div class="text-sm text-on-surface-variant">${escapeHtml(r.explanation)}</div></div></div>`
    : `<div class="card p-4 !border-error/50 bg-error-container/20 flex items-center gap-3"><span class="material-symbols-outlined text-[28px] text-error">gpp_bad</span><div><div class="font-semibold text-error">All repair attempts failed verification</div><button data-action="goto-attempts" class="text-sm text-primary hover:underline">See the ${r.attempts.length} attempts</button></div></div>`;
  const code = r.fixed_code || "";
  const toggle = `<div class="flex items-center justify-between gap-2 flex-wrap">
    <div class="flex bg-surface-container-high p-0.5 rounded">${["code", "diff"].map((v) => `<button data-view="${v}" class="seg px-3 py-1 rounded mono text-[11px] ${state.correctedView === v ? "on" : ""}">${v === "code" ? "Corrected Code" : "Diff View"}</button>`).join("")}</div>
    <span class="mono text-[11px] text-outline">${fixed ? "verified by compiler" : "last rejected candidate"}</span></div>`;
  let body;
  if (!code) body = '<p class="text-sm text-on-surface-variant">The model did not return a usable candidate.</p>';
  else if (state.correctedView === "diff") {
    body = `<div class="codebox !p-0">${lineDiff(state.diagnosisSource ?? state.source, code).map(([sign, text]) => `<div class="px-3 ${sign === "+" ? "diff-add" : sign === "-" ? "diff-del" : ""}"><span class="text-outline select-none inline-block w-4">${sign}</span>${escapeHtml(text) || " "}</div>`).join("")}</div>`;
  } else {
    body = `<div class="codebox">${code.split("\n").map((line, i) => `<span class="text-outline select-none inline-block w-8">${i + 1}</span>${highlightLine(line, null)}`).join("\n")}</div>`;
  }
  const actions = code ? `<div class="flex items-center justify-end gap-2 flex-wrap">
    <button data-action="copy-fix" class="btn btn-ghost"><span class="material-symbols-outlined text-[16px]">content_copy</span>Copy</button>
    <button data-action="download-fix" class="btn btn-ghost"><span class="material-symbols-outlined text-[16px]">download</span>Download .lang</button>
    ${fixed ? '<button data-action="apply-fix" class="btn btn-primary"><span class="material-symbols-outlined text-[16px]">input</span>Apply to Editor</button>' : ""}</div>` : "";
  return banner + toggle + body + actions;
}

function renderRight() {
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("on", tab.dataset.tab === state.tab));
  const body = { errors: renderErrorsTab, attempts: renderAttemptsTab, corrected: renderCorrectedTab }[state.tab]();
  $("rightBody").innerHTML = body;
  const err = currentError();
  const errBadge = $("errBadge");
  errBadge.classList.toggle("hidden", !(state.diagnosis && state.diagnosis.status === "error"));
  errBadge.className = "badge bg-error text-surface" + (state.diagnosis && state.diagnosis.status === "error" ? "" : " hidden");
  errBadge.textContent = "1";
  const attBadge = $("attBadge");
  if (state.repairing) { attBadge.className = "badge bg-primary-container/30 text-primary"; attBadge.textContent = "running"; }
  else if (state.repair) { attBadge.className = "badge bg-surface-container-highest text-on-surface-variant"; attBadge.textContent = String(state.repair.attempts.length); }
  else attBadge.className = "badge hidden";
  $("fixDot").className = "w-2 h-2 rounded-full " + (state.repair ? (state.repair.status === "fixed" ? "bg-tertiary" : "bg-error") : "bg-outline");
  renderStatus(err);
}

function renderStatus(err) {
  const badge = $("statusBadge");
  const d = state.diagnosis;
  const label = !d ? "" : d.status === "ok" ? "Compiled OK" : { LEXICAL: "Lex Failure", SYNTAX: "Parse Failure", SEMANTIC: "Type Error" }[d.error.error_type];
  badge.textContent = state.repairing ? "Repairing…" : label;
  badge.className = "px-1.5 rounded font-mono text-[10px] uppercase " + (!d && !state.repairing ? "hidden" : state.repairing ? "bg-primary-container/30 text-primary" : d.status === "ok" ? "bg-tertiary/15 text-tertiary" : "bg-error-container/40 text-error");
  $("tabErrDot").classList.toggle("hidden", !err);
  $("errorCount").innerHTML = d ? (d.status === "ok" ? '<span class="text-tertiary">● 0 Errors</span> ·' : '<span class="text-error">● 1 Error</span> ·') : "";
  $("modelFooter").innerHTML = `<span class="${state.ollama ? "text-tertiary" : "text-error"}">●</span> Repair model: ${escapeHtml(state.model || "—")}`;
  $("latencyFooter").textContent = d ? `Check: ${d.elapsed_ms.toFixed(1)} ms${state.repair ? ` · Repair: ${state.repair.elapsed.toFixed(1)} s` : ""}` : "";
  for (const id of ["fileName", "crumbFile", "tabFile"]) $(id).textContent = state.fileName;
  $("dirtyDot").classList.toggle("hidden", state.source === state.original);
}

function renderControls() {
  document.querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("on", b.dataset.mode === state.mode));
  $("guardDot").className = "w-2 h-2 rounded-full " + (state.guard ? "bg-tertiary shadow-[0_0_8px_rgba(66,224,154,0.6)]" : "bg-outline");
  $("guardText").textContent = state.guard ? "ON" : "OFF";
  $("guardText").className = "font-mono text-[10px] " + (state.guard ? "text-tertiary" : "text-outline");
  $("mobileControls").innerHTML = `
    <div class="flex bg-surface-container-high p-0.5 rounded">${["ast", "text"].map((m) => `<button data-mode="${m}" class="seg px-2 py-0.5 rounded font-mono text-[11px] ${state.mode === m ? "on" : ""}">${m.toUpperCase()}</button>`).join("")}</div>
    <button data-action="toggle-guard" class="px-2 py-1 rounded bg-surface-container-lowest font-mono text-[11px] ${state.guard ? "text-tertiary" : "text-outline"}">Guard ${state.guard ? "ON" : "OFF"}</button>
    <select data-role="example" class="bg-surface-container-lowest rounded px-2 py-1 text-xs max-w-[180px]">${exampleOptions()}</select>`;
}

function exampleOptions() {
  const groups = {};
  for (const ex of state.examples) (groups[ex.category] ||= []).push(ex);
  return '<option value="">Load Example</option>' + Object.entries(groups).map(([cat, list]) => `<optgroup label="${cat}">${list.map((ex) => `<option value="${escapeHtml(ex.name)}">${escapeHtml(ex.name)} — ${escapeHtml(ex.source.split("\n")[0].slice(0, 28))}</option>`).join("")}</optgroup>`).join("");
}

function render() {
  renderControls();
  renderEditor();
  renderRight();
}

function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.add("hidden"), 2200);
}

async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

let compileSeq = 0;
async function compile(explicit) {
  const seq = ++compileSeq;
  const source = state.source;
  try {
    const result = await api("/api/compile", { source });
    if (seq !== compileSeq) return;
    state.diagnosis = result;
    state.diagnosisSource = source;
    state.stale = false;
    if (explicit) {
      state.showTooltip = result.status === "error";
      state.tab = "errors";
      state.repair = null;
      state.repairError = "";
    }
    render();
  } catch (error) {
    toast("Compile failed: " + error.message);
  }
}

async function repair() {
  if (state.repairing) return;
  if (!currentError()) await compile(false);
  if (!currentError()) { toast("Nothing to repair: the program compiles."); return; }
  state.repairing = true;
  state.repairError = "";
  state.repair = null;
  state.showTooltip = false;
  state.tab = "attempts";
  render();
  try {
    const result = await api("/api/repair", { source: state.diagnosisSource, repair_mode: state.mode, intent_guard: state.guard, model: state.model || null });
    state.repair = result.status === "ok" ? null : result;
    state.tab = result.status === "fixed" ? "corrected" : "attempts";
  } catch (error) {
    state.repairError = error.message + ". Make sure Ollama is running and the model is pulled.";
  } finally {
    state.repairing = false;
    render();
  }
}

function setSource(source, { original = false, name } = {}) {
  state.source = source;
  if (original) state.original = source;
  if (name) state.fileName = name;
  $("editor").value = source;
  state.stale = true;
  scheduleCompile();
  render();
}

let compileTimer;
function scheduleCompile() {
  clearTimeout(compileTimer);
  compileTimer = setTimeout(() => compile(false), 450);
}

function download(name, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

function gotoLine(line, column = 1) {
  const editor = $("editor");
  const lines = state.source.split("\n");
  let offset = 0;
  for (let i = 0; i < line - 1 && i < lines.length; i++) offset += lines[i].length + 1;
  offset += Math.max(0, column - 1);
  editor.focus();
  editor.setSelectionRange(offset, offset);
  $("editorScroll").scrollTop = Math.max(0, (line - 4) * LINE);
  updateCursor();
}

function updateCursor() {
  const editor = $("editor");
  const before = editor.value.slice(0, editor.selectionStart).split("\n");
  $("cursorPos").textContent = `Ln ${before.length}, Col ${before.at(-1).length + 1}`;
}

function loadExample(name) {
  const ex = state.examples.find((e) => e.name === name);
  if (!ex) return;
  state.repair = null;
  state.repairError = "";
  setSource(ex.source, { original: true, name: ex.name.split("/").pop() });
  compile(true);
}

async function handleAction(action) {
  const err = state.diagnosis?.error;
  if (action === "repair") repair();
  else if (action === "close-tip") { state.showTooltip = false; renderTooltip(); }
  else if (action === "goto-errors") { state.tab = "errors"; renderRight(); }
  else if (action === "goto-attempts") { state.tab = "attempts"; renderRight(); }
  else if (action === "goto-line" && err) gotoLine(err.line, err.column || 1);
  else if (action === "toggle-guard") { state.guard = !state.guard; render(); }
  else if (action === "copy-fix") { await navigator.clipboard.writeText(state.repair.fixed_code); toast("Corrected code copied"); }
  else if (action === "download-fix") download(state.fileName.replace(/\.lang$/, "") + ".fixed.lang", state.repair.fixed_code);
  else if (action === "apply-fix") {
    setSource(state.repair.fixed_code.endsWith("\n") ? state.repair.fixed_code : state.repair.fixed_code + "\n");
    toast("Fix applied to editor");
    compile(true);
  }
}

function bind() {
  const editor = $("editor");
  editor.addEventListener("input", () => {
    state.source = editor.value;
    state.stale = true;
    state.showTooltip = false;
    renderEditor();
    renderStatus(null);
    scheduleCompile();
  });
  editor.addEventListener("keydown", (e) => {
    if (e.key === "Tab") {
      e.preventDefault();
      const { selectionStart: s, selectionEnd: t } = editor;
      editor.setRangeText("  ", s, t, "end");
      editor.dispatchEvent(new Event("input"));
    }
  });
  ["keyup", "click", "select"].forEach((ev) => editor.addEventListener(ev, updateCursor));
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); compile(true); }
    if (e.key === "Escape") { state.showTooltip = false; renderTooltip(); }
  });
  $("compileBtn").addEventListener("click", () => compile(true));
  $("uploadBtn").addEventListener("click", () => $("fileInput").click());
  $("fileInput").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    state.repair = null;
    setSource(await file.text(), { original: true, name: file.name });
    compile(true);
    e.target.value = "";
  });
  $("formatBtn").addEventListener("click", async () => {
    try { setSource((await api("/api/format", { source: state.source })).source); toast("Formatted"); }
    catch (error) { toast(error.message); }
  });
  $("copyBtn").addEventListener("click", async () => { await navigator.clipboard.writeText(state.source); toast("Source copied"); });
  $("revertBtn").addEventListener("click", () => { setSource(state.original); toast("Reverted to original"); });
  $("guardToggle").addEventListener("click", () => handleAction("toggle-guard"));
  $("modelSelect").addEventListener("change", (e) => { state.model = e.target.value; renderStatus(currentError()); });
  $("exampleSelect").addEventListener("change", (e) => { loadExample(e.target.value); e.target.value = ""; });
  document.addEventListener("click", (e) => {
    const mode = e.target.closest("[data-mode]");
    if (mode) { state.mode = mode.dataset.mode; render(); return; }
    const tab = e.target.closest("[data-tab]");
    if (tab) { state.tab = tab.dataset.tab; renderRight(); return; }
    const view = e.target.closest("[data-view]");
    if (view) { state.correctedView = view.dataset.view; renderRight(); return; }
    const action = e.target.closest("[data-action]");
    if (action) handleAction(action.dataset.action);
  });
  document.addEventListener("change", (e) => {
    if (e.target.matches('[data-role="example"]')) loadExample(e.target.value);
  });
  window.addEventListener("resize", renderEditor);
  const divider = $("divider");
  divider.addEventListener("mousedown", (e) => {
    e.preventDefault();
    const move = (ev) => {
      const pct = Math.min(75, Math.max(25, (ev.clientX / window.innerWidth) * 100));
      $("leftPanel").style.width = pct + "%";
      renderEditor();
    };
    const up = () => { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  });
}

async function init() {
  bind();
  measureChar();
  document.fonts?.ready.then(() => { measureChar(); renderEditor(); });
  setSource(DEFAULT_SOURCE, { original: true, name: "tc08_demo.lang" });
  try {
    state.examples = await api("/api/examples");
    $("exampleSelect").innerHTML = exampleOptions();
  } catch {}
  compile(true);
  loadHealth();
}

async function loadHealth() {
  try {
    const health = await api("/api/health");
    state.ollama = health.ollama;
    const models = health.models.length ? health.models : ["qwen2.5-coder:7b"];
    state.model = models.includes("qwen2.5-coder:7b") ? "qwen2.5-coder:7b" : models[0];
    $("modelSelect").innerHTML = models.map((m) => `<option value="${escapeHtml(m)}" ${m === state.model ? "selected" : ""}>${escapeHtml(m)}</option>`).join("");
    $("ollamaBadge").textContent = health.ollama ? "Local / Ollama" : "Ollama offline";
    $("ollamaBadge").className = "px-1 rounded text-[10px] " + (health.ollama ? "bg-surface-container-high text-on-surface-variant" : "bg-error-container/50 text-error");
  } catch {}
}

init();
