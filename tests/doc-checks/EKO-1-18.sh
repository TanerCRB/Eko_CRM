#!/usr/bin/env bash
# EKO-1-18 — checks for the agent-session permission rules of Issue #83 (release tags, releases
# and re-runs outside `git push`), criteria K-01..K-05. K-06 and K-07 are judged by the human.
#
#   bash tests/doc-checks/EKO-1-18.sh                    # the working tree against origin/main
#   bash tests/doc-checks/EKO-1-18.sh --head <ref>       # a commit (e.g. the PR head) instead
#   bash tests/doc-checks/EKO-1-18.sh --base <ref> [...] # another base than origin/main
#   bash tests/doc-checks/EKO-1-18.sh --self-test        # built-in contrasts on a throwaway repo
#
# Each check is one line, "ok   <name>", "FAIL <name> — <why>" or "skip <name> — <why>"; "info"
# lines report a decision without counting it (the known over-stops of G-4 A). Exit codes: 0 =
# every check that ran passed, 1 = at least one check failed, 2 = the script itself could not run
# (bad argument, missing or unreadable settings file, not a repository) — never read 2 as a pass.
#
# K-01..K-04 (and the K-05 edges `git push` / `gh pr merge`) evaluate named commands against the
# real `.claude/settings.json` — the working tree file, or the one at --head — under the matcher
# model below, for the Bash tool. K-05 checks that the file keeps the PowerShell tool off (C-10)
# and compares the file and the change set with the base.
#
# ---- matcher model ----------------------------------------------------------------------------
# Read on 2026-11-06 for Claude Code 2.1.319 from https://code.claude.com/docs/en/permissions.md
# ("Permission rule syntax", "Wildcard patterns", "Tool-specific permission rules": Bash,
# Compound commands, Wrappers, What a Bash rule doesn't match) and
# https://code.claude.com/docs/en/tools-reference.md ("Configure tools", "Monitor tool",
# "Bash deny rules also turn off the PowerShell tool"). The model:
#   1. A rule is `Tool` or `Tool(specifier)`; `Tool`, `Tool(*)` and a tool-name glob such as `*`
#      match every call of the tool. Parentheses inside the specifier are literal.
#   2. Rules are evaluated deny, then ask, then allow; the first list with a match decides.
#   3. The specifier matches the whole subcommand text. `*` stands for any text, spaces included.
#      A trailing ` *` that is the rule's only wildcard also matches the bare command (`ls *`
#      matches `ls`), and a trailing `:*` means the same as a trailing ` *`. Without `*` the match
#      is exact.
#   4. Bash (and the Monitor tool, which uses Bash rules): the command is split into subcommands on
#      `&&`, `||`, `;`, `|`, `|&`, `&` and newlines outside quotes, and on subshells, command
#      substitutions and backticks; a deny or ask rule applies when any subcommand matches. Before
#      matching, control-flow keywords, any leading variable assignment (deny and ask rules match
#      past any assignment) and the wrappers `timeout`, `time`, `nice`, `nohup`, `stdbuf`,
#      `command` (not `command -v`), `builtin`, `noglob` and flag-less `xargs` are stripped.
#   5. PowerShell tool (C-10): a `Bash(...)` rule does not restrict the PowerShell tool. On
#      Windows with Git Bash, any Bash deny rule — scoped or bare, in any settings file or
#      `--disallowedTools` — turns the PowerShell tool off for the session, unless
#      `CLAUDE_CODE_USE_POWERSHELL_TOOL=1` is set (environment or a settings `env` block) or a
#      scoped `PowerShell(...)` rule exists (tools-reference, "Bash deny rules also turn off the
#      PowerShell tool"). So the check evaluates no command for the PowerShell tool; K-05 instead
#      requires a Bash deny rule and forbids any `PowerShell` rule and any mention of
#      `CLAUDE_CODE_USE_POWERSHELL_TOOL` in the versioned file. Elsewhere (Linux, macOS, Windows
#      without Git Bash) this rule is not documented and the model claims nothing.
#   6. The documentation does not state whether Bash matching is case-sensitive. A command that
#      must be stopped is evaluated case-sensitively (it must be stopped even if the matcher is
#      strict); a read that must not be stopped is evaluated both ways (it must pass even if the
#      matcher ignores case).
#   7. Not modelled, and not claimed: the program by path or another name (`/usr/bin/gh`,
#      `gh.exe`), `sh -c`/`bash -c`/`env`/aliases/scripts, quoting of the command words, bodies
#      or queries read from a file, user-level/local/managed settings, bypassed permission checks,
#      and a user-level or environment setting that turns the PowerShell tool back on.
#      The model is the documentation's, not the live matcher's (K-07 samples the live matcher).
#
# ---- bases --------------------------------------------------------------------------------------
# The K-05 base is the merge base of --base (origin/main) and the head, so changes on main after
# the task branched are not the task's. Once the task is merged that merge base already holds the
# new rules and the comparison is empty: without --base, when the base settings already deny
# `gh run rerun`, the K-05 comparisons print "skip" with the command to use instead, and are not
# counted. The two C-10 PowerShell checks read the head file alone and are never skipped. After the merge, re-run with main's commit before the merge as base and the PR head:
#
#   bash tests/doc-checks/EKO-1-18.sh --base <merge>^1 --head <merge>^2
#
# With an explicit --base nothing is skipped, and an empty change set fails.

set -uo pipefail

BASE_REF="origin/main"
BASE_GIVEN=""
HEAD_REF=""
SELF_TEST=""
TASK_BASE="0e525b6edb584ca0589cd7d64ae572f8aa9a582c" # origin/main when the task branched
SETTINGS=".claude/settings.json"
LOCAL_SETTINGS=".claude/settings.local.json"
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

die() { echo "EKO-1-18 checks: $* — the checks did not run" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --base) [ $# -ge 2 ] || die "--base needs a ref"; BASE_REF="$2"; BASE_GIVEN=1; shift 2 ;;
    --head) [ $# -ge 2 ] || die "--head needs a ref"; HEAD_REF="$2"; shift 2 ;;
    --self-test) SELF_TEST=1; shift ;;
    *) die "unknown argument '$1' (usage: $0 [--base <ref>] [--head <ref>] | --self-test)" ;;
  esac
done
command -v node >/dev/null 2>&1 || die "node is not on PATH"

# ---- matcher and comparison (Node.js, no dependencies) ------------------------------------------
# Modes: `cases` reads "<id> @@ <want> @@ <tools> @@ <command>" lines on stdin and evaluates them
# against HEAD_JSON; `k05` compares BASE_JSON with HEAD_JSON; `edit` applies a JavaScript body to
# a settings file (self-test only). Exit 2 when a settings text is not the expected JSON shape.
read -r -d '' NODE_PROGRAM <<'JS'
'use strict';
const fs = require('fs');

/** @param {string} what */
function fail2(what) { process.stderr.write(`EKO-1-18 checks: ${what}\n`); process.exit(2); }

/** @param {string|undefined} text @param {string} name */
function load(text, name) {
  let s;
  try { s = JSON.parse(text ?? ''); } catch (e) { fail2(`${name} is not valid JSON (${e.message})`); }
  if (s === null || typeof s !== 'object' || Array.isArray(s)) fail2(`${name} is not a JSON object`);
  const p = s.permissions ?? {};
  if (typeof p !== 'object' || Array.isArray(p)) fail2(`${name}: "permissions" is not an object`);
  for (const k of ['deny', 'ask', 'allow']) {
    if (p[k] !== undefined && !(Array.isArray(p[k]) && p[k].every((r) => typeof r === 'string'))) {
      fail2(`${name}: permissions.${k} is not an array of strings`);
    }
  }
  return s;
}

/** @param {string} r */
function parseRule(r) {
  const open = r.indexOf('(');
  if (open < 0) return { tool: r.trim(), spec: null, text: r };
  if (!r.endsWith(')')) return { tool: r.trim(), spec: null, text: r, broken: true };
  return { tool: r.slice(0, open).trim(), spec: r.slice(open + 1, -1), text: r };
}
/** @param {string} s */
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
/** @param {string} g @param {boolean} ci */
const globRe = (g, ci) => new RegExp('^' + g.split('*').map(esc).join('.*') + '$', ci ? 'is' : 's');
/** @param {string} spec @param {boolean} ci */
function specRe(spec, ci) {
  let s = spec;
  if (s.endsWith(':*')) s = s.slice(0, -2) + ' *';
  const stars = (s.match(/\*/g) || []).length;
  if (stars === 1 && s.endsWith(' *')) {
    return new RegExp('^' + esc(s.slice(0, -2)) + '(?: .*)?$', ci ? 'is' : 's');
  }
  return globRe(s, ci);
}
const PARAM = /^(run_in_background|timeout|description|dangerouslyDisableSandbox)\s*:/;
/** @param {{tool:string,spec:string|null,broken?:boolean}} rule @param {string} tool @param {string} sub @param {boolean} ci */
function ruleMatches(rule, tool, sub, ci) {
  if (rule.broken) return false;
  const toolOk = rule.tool.includes('*') ? globRe(rule.tool, false).test(tool) : rule.tool === tool;
  if (!toolOk) return false;
  if (rule.spec === null || rule.spec.trim() === '*') return true;
  if (PARAM.test(rule.spec)) return false;
  return specRe(rule.spec, ci).test(sub);
}

/** Split a Bash command into subcommands. @param {string} cmd @returns {string[]} */
function splitBash(cmd) {
  const out = []; let cur = ''; let q = null; const stack = [];
  const push = () => { out.push(cur); cur = ''; };
  for (let i = 0; i < cmd.length; i++) {
    const c = cmd[i], n = cmd[i + 1];
    if (q === "'") { cur += c; if (c === "'") q = null; continue; }
    if (q === '"') {
      if (c === '\\') { cur += c + (n ?? ''); i++; continue; }
      if (c === '$' && n === '(') { push(); stack.push(q); q = null; i++; continue; }
      if (c === '`') { push(); stack.push('`' + q); q = null; continue; }
      cur += c; if (c === '"') q = null; continue;
    }
    if (c === '\\') { cur += c + (n ?? ''); i++; continue; }
    if (c === "'" || c === '"') { q = c; cur += c; continue; }
    if ((c === '&' && n === '&') || (c === '|' && n === '|') || (c === '|' && n === '&')) { push(); i++; continue; }
    if (c === ';' || c === '|' || c === '\n' || c === '\r') { push(); continue; }
    if (c === '$' && n === '(') { push(); stack.push(null); i++; continue; }
    if (c === '(') { push(); stack.push(null); continue; }
    if (c === ')') { push(); q = stack.length ? stack.pop() : null; continue; }
    if (c === '`') {
      push();
      const top = stack.length ? stack[stack.length - 1] : undefined;
      if (typeof top === 'string' && top.startsWith('`')) { stack.pop(); q = top.slice(1) || null; }
      else stack.push('`');
      continue;
    }
    if (c === '&') {
      if (cur.endsWith('>') || cur.endsWith('<') || n === '>') { cur += c; continue; }
      push(); continue;
    }
    cur += c;
  }
  push();
  return out;
}
/** @param {string} s */
function stripBash(s) {
  let prev; s = s.trim();
  do {
    prev = s;
    s = s.replace(/^(?:if|then|do|else|elif|while|until|!|\{)\s+/, '');
    s = s.replace(/^[A-Za-z_][A-Za-z0-9_]*=(?:'[^']*'|"(?:[^"\\]|\\.)*"|[^\s'"])*\s+/, '');
    s = s.replace(/^(?:time|nohup|builtin|noglob)\s+/, '');
    s = s.replace(/^command\s+(?!-v\b)/, '');
    s = s.replace(/^timeout\s+(?:-\S+\s+)*\S+\s+/, '');
    s = s.replace(/^nice\s+(?:-n\s+\S+\s+|-\d+\s+)?/, '');
    s = s.replace(/^stdbuf\s+(?:-\S+\s+)*/, '');
    s = s.replace(/^xargs\s+(?!-)/, '');
    s = s.trim();
  } while (s !== prev);
  return s;
}
/** @param {any} settings @param {string} tool @param {string} cmd @param {boolean} ci */
function decide(settings, tool, cmd, ci) {
  const subs = splitBash(cmd).map(stripBash).filter((s) => s.length > 0);
  const p = settings.permissions ?? {};
  for (const list of ['deny', 'ask']) {
    const hits = (p[list] ?? []).filter((r) => subs.some((sub) => ruleMatches(parseRule(r), tool, sub, ci)));
    if (hits.length) return { list, hits };
  }
  return { list: 'none', hits: [] };
}
const show = (d) => (d.list === 'none' ? 'no deny or ask rule' : `${d.list} ${d.hits.join(', ')}`);

function runCases() {
  const settings = load(process.env.HEAD_JSON, 'the head settings file');
  const lines = fs.readFileSync(0, 'utf8').split(/\r?\n/).filter((l) => l.trim() && !l.startsWith('#'));
  let failed = 0;
  for (const line of lines) {
    const parts = line.split(' @@ ');
    if (parts.length < 4) fail2(`bad case line: ${line}`);
    const [id, want, toolSpec] = parts.map((x) => x.trim());
    const cmd = parts.slice(3).join(' @@ ');
    // Bash only (C-10): the Monitor tool uses the same rules, and the PowerShell tool stays off.
    if (toolSpec !== 'Bash') fail2(`tool '${toolSpec}' is not evaluated (Bash only, C-10) in: ${line}`);
    for (const tool of [toolSpec]) {
      const strict = decide(settings, tool, cmd, false);
      const loose = decide(settings, tool, cmd, true);
      let ok, name, why;
      if (want === 'deny') {
        name = `${id} stops [${tool}] ${cmd}`;
        ok = strict.list === 'deny';
        why = strict.list === 'ask' ? `matched ask rule only (${strict.hits.join(', ')}), not deny` : 'no deny rule matches';
      } else if (want === 'ask') {
        name = `${id} asks [${tool}] ${cmd}`;
        ok = strict.list === 'ask' && loose.list !== 'deny';
        if (strict.list === 'none') why = 'no ask rule matches';
        else if (strict.list === 'deny') why = `a deny rule matches (${strict.hits.join(', ')})`;
        else why = `a deny rule matches when case is ignored (${loose.hits.join(', ')})`;
      } else if (want === 'clear') {
        name = `${id} lets through [${tool}] ${cmd}`;
        const hit = strict.list !== 'none' ? strict : loose;
        ok = strict.list === 'none' && loose.list === 'none';
        why = `${show(hit)}${strict.list === 'none' ? ' (when case is ignored)' : ''}`;
      } else if (want === 'info') {
        console.log(`info ${id} [${tool}] ${cmd} — ${show(strict)}`);
        continue;
      } else fail2(`bad want '${want}' in: ${line}`);
      if (ok) console.log(`ok   ${name} — ${want === 'clear' ? 'no deny or ask rule' : show(strict)}`);
      else { console.log(`FAIL ${name} — ${why}`); failed++; }
    }
  }
}

/** @param {any} v */
function canon(v) {
  if (Array.isArray(v)) return '[' + v.map(canon).join(',') + ']';
  if (v && typeof v === 'object') return '{' + Object.keys(v).sort().map((k) => JSON.stringify(k) + ':' + canon(v[k])).join(',') + '}';
  return JSON.stringify(v);
}

function k05() {
  const base = load(process.env.BASE_JSON, 'the base settings file');
  const head = load(process.env.HEAD_JSON, 'the head settings file');
  const bp = base.permissions ?? {}, hp = head.permissions ?? {};
  const report = (name, problems) => {
    if (problems.length === 0) console.log(`ok   ${name}`);
    else console.log(`FAIL ${name} — ${problems.join('; ')}`);
  };

  const kept = [];
  for (const [k, v] of Object.entries(bp)) {
    if (!Array.isArray(v)) continue;
    const hv = Array.isArray(hp[k]) ? hp[k] : [];
    for (const r of v) if (!hv.includes(r)) kept.push(`base permissions.${k} entry ${JSON.stringify(r)} is missing`);
  }
  report('K-05 base deny and ask entries kept unchanged', kept);

  report('K-05 hooks unchanged', canon(base.hooks) === canon(head.hooks) ? [] : ['the "hooks" value differs from the base']);

  const added = [];
  for (const [k, v] of Object.entries(hp)) {
    if (!Array.isArray(v)) continue;
    const bv = Array.isArray(bp[k]) ? bp[k] : [];
    for (const r of v) {
      if (bv.includes(r)) continue;
      const pr = parseRule(r);
      if (k === 'deny') {
        if (pr.tool !== 'Bash' || pr.spec === null || pr.spec.trim() === '*' || pr.broken) {
          added.push(`added deny entry ${JSON.stringify(r)} is not a scoped Bash(...) rule`);
        }
      } else {
        added.push(`entry ${JSON.stringify(r)} added to permissions.${k}`);
      }
    }
  }
  report('K-05 only scoped Bash deny entries added', added);

  const keys = [];
  for (const k of ['allow', 'defaultMode']) if (k in hp) keys.push(`permissions.${k} is present`);
  for (const k of Object.keys(hp)) if (!(k in bp) && !['allow', 'defaultMode'].includes(k)) keys.push(`permissions.${k} is new`);
  for (const k of Object.keys(head)) {
    if (k === 'permissions' || k === 'hooks') continue;
    if (!(k in base)) keys.push(`top-level key "${k}" is new`);
    else if (canon(base[k]) !== canon(head[k])) keys.push(`top-level key "${k}" changed`);
  }
  report('K-05 no allow, defaultMode or other key added', keys);
}

/**
 * Every path in a JSON value where `pred` holds.
 * @param {any} v @param {(k: string|null, v: any) => boolean} pred
 * @param {string} path @param {string|null} key @param {string[]} out @returns {string[]}
 */
function findAll(v, pred, path = '', key = null, out = []) {
  if (pred(key, v)) out.push(path || '(root)');
  if (Array.isArray(v)) v.forEach((x, i) => findAll(x, pred, `${path}[${i}]`, null, out));
  else if (v && typeof v === 'object') for (const [k, x] of Object.entries(v)) findAll(x, pred, `${path}.${k}`, k, out);
  return out;
}

/** C-10: the head file keeps the PowerShell tool off under model rule 5. */
function powershellOff() {
  const head = load(process.env.HEAD_JSON, 'the head settings file');
  const hp = head.permissions ?? {};
  const report = (name, problems) => {
    if (problems.length === 0) console.log(`ok   ${name}`);
    else console.log(`FAIL ${name} — ${problems.join('; ')}`);
  };
  // A rule whose tool name, or tool-name glob, could name the PowerShell tool, in any list.
  const ps = [];
  for (const [k, v] of Object.entries(hp)) {
    if (!Array.isArray(v)) continue;
    for (const r of v) {
      if (typeof r !== 'string') continue;
      const t = parseRule(r).tool;
      if (/powershell/i.test(t) || (t.includes('*') && globRe(t, true).test('PowerShell'))) {
        ps.push(`permissions.${k} holds ${JSON.stringify(r)}`);
      }
    }
  }
  const bashDeny = (hp.deny ?? []).some((r) => { const pr = parseRule(r); return pr.tool === 'Bash' && !pr.broken; });
  if (!bashDeny) ps.push('permissions.deny holds no Bash rule, so the documented PowerShell-off condition does not hold');
  report('K-05 no PowerShell rule in any permission list, and a Bash deny rule present', ps);
  const env = findAll(head, (k, v) => (k !== null && /CLAUDE_CODE_USE_POWERSHELL_TOOL/i.test(k)) ||
    (typeof v === 'string' && /CLAUDE_CODE_USE_POWERSHELL_TOOL/i.test(v)));
  report('K-05 no CLAUDE_CODE_USE_POWERSHELL_TOOL setting',
    env.map((at) => `CLAUDE_CODE_USE_POWERSHELL_TOOL appears at ${at}`));
}

function edit() {
  const file = process.argv[2];
  const s = JSON.parse(fs.readFileSync(file, 'utf8'));
  const p = s.permissions;
  const del = (list, r) => { const i = p[list].indexOf(r); if (i < 0) fail2(`self-test: ${r} not in ${list}`); p[list].splice(i, 1); };
  new Function('s', 'p', 'del', process.argv[3])(s, p, del);
  fs.writeFileSync(file, JSON.stringify(s, null, 2) + '\n');
}

const mode = process.argv[1];
if (mode === 'cases') runCases();
else if (mode === 'k05') k05();
else if (mode === 'psoff') powershellOff();
else if (mode === 'edit') edit();
else fail2(`unknown node mode '${mode}'`);
JS

run_node() { MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' node -e "$NODE_PROGRAM" "$@"; }

# ---- named commands -----------------------------------------------------------------------------
# "<criterion> @@ deny|ask|clear|info @@ Bash @@ <command>". `deny`: the command must be stopped by
# a deny rule; `ask`: it must meet an ask rule and no deny rule; `clear`: no deny or ask rule may
# match; `info`: reported, not counted. The tool is always Bash (C-10: the Monitor tool uses the
# same rules; the PowerShell tool stays off, model rule 5). Placeholders of the criteria are replaced by synthetic values: <sha> by
# 0123456789abcdef0123456789abcdef01234567, <dir> by ../Eko_CRM-EKO-1-18, GraphQL ids by
# invented R_kgDOexample / REF_kwDOexample. No command here is ever executed.
CASES="$(cat <<'CASES'
# K-01 — gh release create in every form, and the publishing gh release edit (G-3 A).
K-01 @@ deny @@ Bash @@ gh release create v1.0.0
K-01 @@ deny @@ Bash @@ gh release create probe --draft
K-01 @@ deny @@ Bash @@ gh release create
K-01 @@ deny @@ Bash @@ gh release -R TanerCRB/Eko_CRM create v1.0.0
K-01 @@ deny @@ Bash @@ cd ../Eko_CRM-EKO-1-18 && gh release create v1.0.0
K-01 @@ deny @@ Bash @@ gh release edit v1.0.0 --draft=false
K-01 @@ deny @@ Bash @@ gh release -R TanerCRB/Eko_CRM edit probe --draft=false
K-01 @@ clear @@ Bash @@ gh release view v1.0.0
K-01 @@ clear @@ Bash @@ gh release list
# K-02 — gh api writes to git refs, git tags and releases; GraphQL ref mutations (G-5 A).
K-02 @@ deny @@ Bash @@ gh api -X POST repos/{owner}/{repo}/git/refs -f ref=refs/tags/v1.0.0 -f sha=0123456789abcdef0123456789abcdef01234567
K-02 @@ deny @@ Bash @@ gh api repos/TanerCRB/Eko_CRM/git/refs -f ref=refs/tags/v1.0.0 -f sha=0123456789abcdef0123456789abcdef01234567
K-02 @@ deny @@ Bash @@ gh api --method PATCH /repos/{owner}/{repo}/git/refs/tags/v1.0.0 -f sha=0123456789abcdef0123456789abcdef01234567 -F force=true
K-02 @@ deny @@ Bash @@ gh api repos/{owner}/{repo}/git/tags -f tag=v1.0.0 -f object=0123456789abcdef0123456789abcdef01234567 -f type=commit -f message=m
K-02 @@ deny @@ Bash @@ gh api repos/{owner}/{repo}/releases -f tag_name=v1.0.0
K-02 @@ deny @@ Bash @@ gh api -X PATCH repos/{owner}/{repo}/releases/123 -F draft=false
K-02 @@ deny @@ Bash @@ gh api graphql -f query='mutation { createRef(input: {repositoryId: "R_kgDOexample", name: "refs/tags/probe", oid: "0123456789abcdef0123456789abcdef01234567"}) { ref { name } } }'
K-02 @@ deny @@ Bash @@ gh api graphql -f query='mutation { updateRef(input: {refId: "REF_kwDOexample", oid: "0123456789abcdef0123456789abcdef01234567", force: true}) { ref { name } } }'
K-02 @@ deny @@ Bash @@ gh api graphql -f query='mutation { updateRefs(input: {repositoryId: "R_kgDOexample", refUpdates: []}) { clientMutationId } }'
K-02 @@ deny @@ Bash @@ gh api -XPOST repos/{owner}/{repo}/git/refs -f ref=refs/tags/probe -f sha=0123456789abcdef0123456789abcdef01234567
K-02 @@ deny @@ Bash @@ gh api --method=POST repos/{owner}/{repo}/git/refs -f ref=refs/tags/probe -f sha=0123456789abcdef0123456789abcdef01234567
K-02 @@ deny @@ Bash @@ gh api -X post repos/{owner}/{repo}/releases -f tag_name=probe
K-02 @@ deny @@ Bash @@ gh api repos/{owner}/{repo}/git/refs --method POST -f ref=refs/tags/probe -f sha=0123456789abcdef0123456789abcdef01234567
K-02 @@ deny @@ Bash @@ gh api repos/{owner}/{repo}/git/refs --raw-field ref=refs/tags/probe --raw-field sha=0123456789abcdef0123456789abcdef01234567
K-02 @@ deny @@ Bash @@ gh api repos/{owner}/{repo}/git/refs --field ref=refs/tags/probe --field sha=0123456789abcdef0123456789abcdef01234567
K-02 @@ deny @@ Bash @@ gh api repos/{owner}/{repo}/git/refs --input ref.json
K-02 @@ deny @@ Bash @@ gh api repos/tanercrb/eko_crm/releases -f tag_name=probe
K-02 @@ deny @@ Bash @@ gh api -iXPOST repos/{owner}/{repo}/git/refs -f ref=refs/tags/probe -f sha=0123456789abcdef0123456789abcdef01234567
K-02 @@ clear @@ Bash @@ gh api repos/{owner}/{repo}/releases/latest
K-02 @@ clear @@ Bash @@ gh api repos/{owner}/{repo}/git/refs/tags/v1.0.0
K-02 @@ clear @@ Bash @@ gh api user --jq .login
K-02 @@ clear @@ Bash @@ OPERATOR=$(gh api user --jq .login)
K-02 known over-stop (G-4 A) @@ info @@ Bash @@ gh api graphql -f query='query { viewer { login } }'
K-02 known over-stop (G-4 A) @@ info @@ Bash @@ gh api -X GET repos/{owner}/{repo}/git/refs/tags -f per_page=100
K-02 known over-stop (G-4 A) @@ info @@ Bash @@ gh api repos/{owner}/{repo}/releases/latest --jq .tag_name
# K-03 — gh run rerun in every form.
K-03 @@ deny @@ Bash @@ gh run rerun
K-03 @@ deny @@ Bash @@ gh run rerun 123
K-03 @@ deny @@ Bash @@ gh run rerun 123 --failed
K-03 @@ deny @@ Bash @@ gh run rerun --job 456
K-03 @@ deny @@ Bash @@ gh run rerun 123 --debug
K-03 @@ deny @@ Bash @@ gh run -R TanerCRB/Eko_CRM rerun 123
K-03 @@ deny @@ Bash @@ gh run -R TanerCRB/Eko_CRM rerun
K-03 @@ deny @@ Bash @@ cd ../Eko_CRM-EKO-1-18 && gh run rerun 123
K-03 @@ clear @@ Bash @@ gh run view 123
K-03 @@ clear @@ Bash @@ gh run view 123 --log-failed
K-03 @@ clear @@ Bash @@ gh run list
# K-04 — gh api to the three re-run endpoints, whatever the method, and the re-request paths (G-5 A).
K-04 @@ deny @@ Bash @@ gh api -X POST repos/{owner}/{repo}/actions/runs/123/rerun
K-04 @@ deny @@ Bash @@ gh api repos/TanerCRB/Eko_CRM/actions/runs/123/rerun-failed-jobs -F enable_debug_logging=true
K-04 @@ deny @@ Bash @@ gh api --method POST /repos/{owner}/{repo}/actions/jobs/456/rerun
K-04 @@ deny @@ Bash @@ gh api repos/{owner}/{repo}/actions/runs/123/rerun
K-04 @@ deny @@ Bash @@ gh api /repos/{owner}/{repo}/actions/runs/123/rerun-failed-jobs
K-04 @@ deny @@ Bash @@ gh api repos/TanerCRB/Eko_CRM/actions/jobs/456/rerun -X POST
K-04 @@ deny @@ Bash @@ gh api -X POST repos/{owner}/{repo}/check-suites/789/rerequest
K-04 @@ deny @@ Bash @@ gh api -X POST repos/{owner}/{repo}/check-runs/789/rerequest
K-04 @@ deny @@ Bash @@ gh api graphql -f query='mutation { rerequestCheckSuite(input: {repositoryId: "R_kgDOexample", checkSuiteId: "CS_kwDOexample"}) { checkSuite { id } } }'
K-04 @@ clear @@ Bash @@ gh api repos/{owner}/{repo}/actions/runs/123
K-04 @@ clear @@ Bash @@ gh api repos/{owner}/{repo}/actions/runs/123/jobs
K-04 @@ clear @@ Bash @@ gh api repos/{owner}/{repo}/actions/jobs/456
# K-05 edges — the existing rules keep their effect, and the new deny rules do not swallow git push.
K-05 @@ ask @@ Bash @@ git push origin EKO-1-18-release-permission-rules
K-05 @@ deny @@ Bash @@ gh pr merge 85
K-05 @@ deny @@ Bash @@ git push --force origin EKO-1-18-release-permission-rules
CASES
)"

# ---- self-test ----------------------------------------------------------------------------------
# The settings file at the task base (TASK_BASE), and the proposal the developer report gives the
# human. The self-test proves the proposal passes and that each contrast fails, on a throwaway
# repository, against a pre-merge base and against a post-merge base.
BASE_SETTINGS="$(cat <<'JSON'
{
  "permissions": {
    "deny": ["Bash(gh pr merge:*)", "Bash(git push --force:*)", "Bash(git push -f:*)"],
    "ask": ["Bash(git push:*)"]
  },
  "hooks": {
    "SessionStart": [
      { "matcher": "startup|clear|compact",
        "hooks": [ { "type": "command",
                     "command": "bash \"$CLAUDE_PROJECT_DIR/scripts/task-journal-context.sh\"" } ] }
    ],
    "SubagentStop": [
      { "hooks": [ { "type": "command",
                     "command": "node \"$CLAUDE_PROJECT_DIR/scripts/cost-capture.mjs\"" } ] }
    ]
  }
}
JSON
)"
PROPOSED_SETTINGS="$(cat <<'JSON'
{
  "permissions": {
    "deny": ["Bash(gh pr merge:*)", "Bash(git push --force:*)", "Bash(git push -f:*)",
             "Bash(gh release create *)", "Bash(gh release * create)", "Bash(gh release * create *)",
             "Bash(gh release edit *)", "Bash(gh release * edit)", "Bash(gh release * edit *)",
             "Bash(gh api*/git/* -*)", "Bash(gh api* -*/git/*)",
             "Bash(gh api*/releases* -*)", "Bash(gh api* -*/releases*)",
             "Bash(gh api*graphql*)",
             "Bash(gh run rerun *)", "Bash(gh run * rerun)", "Bash(gh run * rerun *)",
             "Bash(gh api*/actions/runs/*/rerun*)", "Bash(gh api*/actions/jobs/*/rerun*)",
             "Bash(gh api*/check-suites/*/rerequest*)", "Bash(gh api*/check-runs/*/rerequest*)"],
    "ask": ["Bash(git push:*)"]
  },
  "hooks": {
    "SessionStart": [
      { "matcher": "startup|clear|compact",
        "hooks": [ { "type": "command",
                     "command": "bash \"$CLAUDE_PROJECT_DIR/scripts/task-journal-context.sh\"" } ] }
    ],
    "SubagentStop": [
      { "hooks": [ { "type": "command",
                     "command": "node \"$CLAUDE_PROJECT_DIR/scripts/cost-capture.mjs\"" } ] }
    ]
  }
}
JSON
)"

self_test() {
  local root failures=0 total=0
  root="$(mktemp -d)" || die "mktemp failed"
  # shellcheck disable=SC2064
  trap "rm -rf '$root'" EXIT

  # fresh — a throwaway repository: main holds the base settings, branch `task` the proposal and
  # the bookkeeping changes the task is allowed (a plan entry and a cost row).
  fresh() {
    rm -rf "$root/repo" && mkdir -p "$root/repo" && cd "$root/repo" || return 1
    git init -q -b main
    git config user.email t@example.invalid && git config user.name t && git config core.autocrlf false
    mkdir -p .claude tests/doc-checks docs/cost-register .github/workflows
    printf '%s\n' "$BASE_SETTINGS" > "$SETTINGS"
    cp "$SELF" tests/doc-checks/EKO-1-18.sh
    printf '# Plan\n' > docs/PLAN.md
    printf 'on:\n  push:\n    tags: ["v*"]\n' > .github/workflows/release.yml
    printf '%s\n' "$LOCAL_SETTINGS" > .gitignore
    git add -A && git commit -qm base
    git checkout -q -b task
    printf '%s\n' "$PROPOSED_SETTINGS" > "$SETTINGS"
    printf -- '- [ ] **EKO-1-18** — reserved\n' >> docs/PLAN.md
    printf '{"row": 1}\n' > docs/cost-register/2026-11-06_EKO-1-18_analysis_analyst_1.json
    git add -A && git commit -qm task
  }
  edit_settings() { run_node edit "$SETTINGS" "$1" || return 1; }

  # verdict <name> <expected exit> <text the output must contain> <command...>
  verdict() {
    local name="$1" want="$2" must="$3" out code
    shift 3
    total=$((total + 1))
    out="$("$@" 2>&1)"
    code=$?
    if [ "$code" -ne "$want" ]; then
      echo "FAIL $name — expected exit $want, got $code"
      printf '%s\n' "$out" | grep -E '^(FAIL|skip)' | head -5 | sed 's/^/       /'
      failures=$((failures + 1))
    elif [ -n "$must" ] && ! grep -qF -- "$must" <<< "$out"; then
      echo "FAIL $name — output lacks '$must'"
      failures=$((failures + 1))
    else
      echo "ok   $name"
    fi
  }
  # expect <name> <expected exit> <change on branch task> <text the output must contain>
  # Runs the check pre-merge (--base main --head task) and post-merge (task merged into main with
  # --no-ff, then --base <merge>^1 --head <merge>^2).
  expect() {
    local name="$1" want="$2" change="$3" must="${4:-}"
    fresh || { echo "FAIL $name — fixture"; failures=$((failures + 1)); return; }
    eval "$change" || { echo "FAIL $name — change did not apply"; failures=$((failures + 1)); return; }
    git add -A && git commit -qm change --allow-empty
    verdict "$name (pre-merge base)" "$want" "$must" bash tests/doc-checks/EKO-1-18.sh --base main --head task
    git checkout -q main && git merge -q --no-ff task -m merge
    verdict "$name (post-merge base)" "$want" "$must" bash tests/doc-checks/EKO-1-18.sh --base HEAD^1 --head HEAD^2
  }

  # Must pass.
  expect "the proposed settings pass" 0 ":"
  fresh
  verdict "working-tree mode on the task branch passes" 0 "ok   K-05 change set limited" \
    bash tests/doc-checks/EKO-1-18.sh --base main
  git checkout -q main && git merge -q --no-ff task -m merge && git update-ref refs/remotes/origin/main HEAD
  verdict "after the merge, the default base skips K-05 by name and passes" 0 \
    "skip K-05 change set limited to the allowed files" bash tests/doc-checks/EKO-1-18.sh --head HEAD
  verdict "after the merge, an explicit base containing the head fails" 1 "change set is empty" \
    bash tests/doc-checks/EKO-1-18.sh --base HEAD --head HEAD

  # Must fail: the base file itself (no rule exists yet).
  expect "the base settings fail K-01..K-04" 1 "printf '%s\n' \"\$BASE_SETTINGS\" > $SETTINGS" \
    "FAIL K-04 stops [Bash] gh api -X POST repos/{owner}/{repo}/actions/runs/123/rerun"

  # Must fail: K-01 mutations.
  expect "K-01 rule deleted" 1 "edit_settings 'del(\"deny\",\"Bash(gh release create *)\")'" \
    "FAIL K-01 stops [Bash] gh release create v1.0.0"
  expect "K-01 narrowed to release-form names" 1 \
    "edit_settings 'del(\"deny\",\"Bash(gh release create *)\"); p.deny.push(\"Bash(gh release create v*)\")'" \
    "FAIL K-01 stops [Bash] gh release create probe --draft"
  expect "K-01 narrowed to the form without a flag before the subcommand" 1 \
    "edit_settings 'del(\"deny\",\"Bash(gh release * create *)\")'" \
    "FAIL K-01 stops [Bash] gh release -R TanerCRB/Eko_CRM create v1.0.0"
  expect "K-01 widened to the whole gh release group" 1 "edit_settings 'p.deny.push(\"Bash(gh release *)\")'" \
    "FAIL K-01 lets through [Bash] gh release list"
  expect "K-01 moved from deny to ask" 1 \
    "edit_settings 'del(\"deny\",\"Bash(gh release create *)\"); p.ask.push(\"Bash(gh release create *)\")'" \
    "matched ask rule only"
  expect "K-01 publishing-edit rule deleted" 1 "edit_settings 'del(\"deny\",\"Bash(gh release edit *)\")'" \
    "FAIL K-01 stops [Bash] gh release edit v1.0.0 --draft=false"

  # Must fail: K-02 mutations.
  expect "K-02 implicit-POST rule deleted" 1 "edit_settings 'del(\"deny\",\"Bash(gh api*/git/* -*)\")'" \
    "FAIL K-02 stops [Bash] gh api repos/TanerCRB/Eko_CRM/git/refs"
  expect "K-02 narrowed to the -X POST spelling" 1 \
    "edit_settings 'for (const r of [\"Bash(gh api*/git/* -*)\",\"Bash(gh api* -*/git/*)\",\"Bash(gh api*/releases* -*)\",\"Bash(gh api* -*/releases*)\"]) del(\"deny\", r); p.deny.push(\"Bash(gh api -X POST *)\")'" \
    "FAIL K-02 stops [Bash] gh api --method PATCH"
  expect "K-02 narrowed to the placeholder form" 1 \
    "edit_settings 'for (const r of [\"Bash(gh api*/git/* -*)\",\"Bash(gh api* -*/git/*)\"]) del(\"deny\", r); p.deny.push(\"Bash(gh api*{owner}/{repo}/git/* -*)\", \"Bash(gh api* -*{owner}/{repo}/git/*)\")'" \
    "FAIL K-02 stops [Bash] gh api repos/TanerCRB/Eko_CRM/git/refs"
  expect "K-02 GraphQL rule deleted" 1 "edit_settings 'del(\"deny\",\"Bash(gh api*graphql*)\")'" \
    "FAIL K-02 stops [Bash] gh api graphql -f query='mutation { createRef"
  expect "K-02 widened to the whole of gh api" 1 "edit_settings 'p.deny.push(\"Bash(gh api *)\")'" \
    "FAIL K-02 lets through [Bash] gh api user --jq .login"
  expect "K-02 moved from deny to ask" 1 \
    "edit_settings 'del(\"deny\",\"Bash(gh api*graphql*)\"); p.ask.push(\"Bash(gh api*graphql*)\")'" \
    "matched ask rule only"

  # Must fail: K-03 mutations.
  expect "K-03 rule deleted" 1 "edit_settings 'del(\"deny\",\"Bash(gh run rerun *)\")'" \
    "FAIL K-03 stops [Bash] gh run rerun 123"
  expect "K-03 narrowed to forms with a run id" 1 \
    "edit_settings 'del(\"deny\",\"Bash(gh run rerun *)\"); p.deny.push(\"Bash(gh run rerun [0-9]*)\")'" \
    "FAIL K-03 stops [Bash] gh run rerun — "
  expect "K-03 narrowed to --failed" 1 \
    "edit_settings 'del(\"deny\",\"Bash(gh run rerun *)\"); p.deny.push(\"Bash(gh run rerun *--failed*)\")'" \
    "FAIL K-03 stops [Bash] gh run rerun 123 — "
  expect "K-03 widened to the whole gh run group" 1 "edit_settings 'p.deny.push(\"Bash(gh run *)\")'" \
    "FAIL K-03 lets through [Bash] gh run list"
  expect "K-03 keyed to the word failed" 1 "edit_settings 'p.deny.push(\"Bash(gh run *failed*)\")'" \
    "FAIL K-03 lets through [Bash] gh run view 123 --log-failed"

  # Must fail: K-04 mutations.
  expect "K-04 jobs re-run rule deleted" 1 "edit_settings 'del(\"deny\",\"Bash(gh api*/actions/jobs/*/rerun*)\")'" \
    "FAIL K-04 stops [Bash] gh api --method POST /repos/{owner}/{repo}/actions/jobs/456/rerun"
  expect "K-04 runs re-run rule narrowed past rerun-failed-jobs" 1 \
    "edit_settings 'del(\"deny\",\"Bash(gh api*/actions/runs/*/rerun*)\"); p.deny.push(\"Bash(gh api*/actions/runs/*/rerun)\")'" \
    "FAIL K-04 stops [Bash] gh api repos/TanerCRB/Eko_CRM/actions/runs/123/rerun-failed-jobs"
  expect "K-04 check-runs rule deleted" 1 "edit_settings 'del(\"deny\",\"Bash(gh api*/check-runs/*/rerequest*)\")'" \
    "FAIL K-04 stops [Bash] gh api -X POST repos/{owner}/{repo}/check-runs/789/rerequest"
  expect "K-04 widened to all of actions/runs" 1 "edit_settings 'p.deny.push(\"Bash(gh api*/actions/runs*)\")'" \
    "FAIL K-04 lets through [Bash] gh api repos/{owner}/{repo}/actions/runs/123"

  # Must fail: K-05 contrasts of the criteria, and the C-10 PowerShell contrasts.
  expect "K-05 git push ask changed to deny" 1 \
    "edit_settings 'del(\"ask\",\"Bash(git push:*)\"); p.deny.push(\"Bash(git push:*)\")'" \
    "FAIL K-05 base deny and ask entries kept unchanged"
  expect "K-05 SubagentStop hook dropped" 1 "edit_settings 'delete s.hooks.SubagentStop'" "FAIL K-05 hooks unchanged"
  expect "K-05 allow entry added" 1 "edit_settings 's.permissions.allow = [\"Bash(gh run list:*)\"]'" \
    "FAIL K-05 no allow, defaultMode or other key added"
  expect "K-05 defaultMode added" 1 "edit_settings 's.permissions.defaultMode = \"acceptEdits\"'" \
    "FAIL K-05 no allow, defaultMode or other key added"
  expect "K-05 settings.local.json tracked" 1 \
    "printf '{}\n' > $LOCAL_SETTINGS && git add -f $LOCAL_SETTINGS" "FAIL K-05 settings.local.json not tracked"
  expect "K-05 release workflow edited" 1 "printf '# edited\n' >> .github/workflows/release.yml" \
    "FAIL K-05 change set limited to the allowed files"
  expect "K-05 an added ask entry" 1 "edit_settings 'p.ask.push(\"Bash(gh release upload *)\")'" \
    "FAIL K-05 only scoped Bash deny entries added"
  expect "K-05 a new deny rule that swallows git push" 1 "edit_settings 'p.deny.push(\"Bash(git *)\")'" \
    "FAIL K-05 asks [Bash] git push origin"
  expect "K-05 a PowerShell deny rule added" 1 "edit_settings 'p.deny.push(\"PowerShell(gh release create *)\")'" \
    "FAIL K-05 no PowerShell rule in any permission list"
  expect "K-05 a PowerShell ask rule added" 1 "edit_settings 'p.ask.push(\"PowerShell(git push:*)\")'" \
    "FAIL K-05 no PowerShell rule in any permission list"
  expect "K-05 a PowerShell allow rule added" 1 "edit_settings 's.permissions.allow = [\"PowerShell(gh run list *)\"]'" \
    "FAIL K-05 no PowerShell rule in any permission list"
  expect "K-05 a tool-name glob that names PowerShell added" 1 "edit_settings 'p.deny.push(\"Power*(gh run rerun *)\")'" \
    "FAIL K-05 no PowerShell rule in any permission list"
  expect "K-05 CLAUDE_CODE_USE_POWERSHELL_TOOL set in an env block" 1 \
    "edit_settings 's.env = { CLAUDE_CODE_USE_POWERSHELL_TOOL: \"1\" }'" \
    "FAIL K-05 no CLAUDE_CODE_USE_POWERSHELL_TOOL setting"
  expect "K-05 CLAUDE_CODE_USE_POWERSHELL_TOOL set in a hook command" 1 \
    "edit_settings 's.hooks.SessionStart[0].hooks[0].command = \"CLAUDE_CODE_USE_POWERSHELL_TOOL=1 \" + s.hooks.SessionStart[0].hooks[0].command'" \
    "FAIL K-05 no CLAUDE_CODE_USE_POWERSHELL_TOOL setting"
  # After the merge the default base makes the base comparison inert; the PowerShell checks are a
  # property of the head file and must still fail.
  fresh
  edit_settings 'p.deny.push("PowerShell(gh release create *)"); s.env = { CLAUDE_CODE_USE_POWERSHELL_TOOL: "1" }'
  git add -A && git commit -qm change
  git checkout -q main && git merge -q --no-ff task -m merge && git update-ref refs/remotes/origin/main HEAD
  verdict "after the merge, the default base still fails on a PowerShell rule" 1 \
    "FAIL K-05 no PowerShell rule in any permission list" bash tests/doc-checks/EKO-1-18.sh --head HEAD
  verdict "after the merge, the default base still fails on the env setting" 1 \
    "FAIL K-05 no CLAUDE_CODE_USE_POWERSHELL_TOOL setting" bash tests/doc-checks/EKO-1-18.sh --head HEAD

  cd / || true
  echo "EKO-1-18 self-test: $((total - failures)) of $total passed"
  [ "$failures" -eq 0 ]
}

if [ -n "$SELF_TEST" ]; then
  [ -z "$BASE_GIVEN$HEAD_REF" ] || die "--self-test takes no other argument"
  self_test
  exit $?
fi

# ---- the checks ---------------------------------------------------------------------------------
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || die "cannot enter the repository root"
git rev-parse --show-toplevel >/dev/null 2>&1 || die "not a git repository"
git rev-parse --verify --quiet "$BASE_REF^{commit}" >/dev/null || die "base '$BASE_REF' is not a commit"
if [ -n "$HEAD_REF" ]; then
  git rev-parse --verify --quiet "$HEAD_REF^{commit}" >/dev/null || die "head '$HEAD_REF' is not a commit"
fi
MB="$(git merge-base "$BASE_REF" "${HEAD_REF:-HEAD}")" || die "no merge base of '$BASE_REF' and '${HEAD_REF:-HEAD}'"

if [ -z "$HEAD_REF" ]; then
  [ -r "$SETTINGS" ] || die "cannot read $SETTINGS"
  HEAD_JSON="$(tr -d '\r' < "$SETTINGS")"
else
  HEAD_JSON="$(git show "$HEAD_REF:$SETTINGS" 2>/dev/null | tr -d '\r')"
  [ -n "$HEAD_JSON" ] || die "$SETTINGS does not exist at $HEAD_REF"
fi
BASE_JSON="$(git show "$MB:$SETTINGS" 2>/dev/null | tr -d '\r')"
[ -n "$BASE_JSON" ] || die "$SETTINGS does not exist at the merge base $MB"
export HEAD_JSON BASE_JSON

OUT="$(printf '%s\n' "$CASES" | run_node cases)" || die "the matcher could not evaluate the settings"
printf '%s\n' "$OUT"
passed="$(grep -c '^ok ' <<< "$OUT")"
failed="$(grep -c '^FAIL ' <<< "$OUT")"

# K-05, C-10: the file keeps the PowerShell tool off (model rule 5). A property of the head file
# alone, so it also runs after the merge, when the base comparison below is inert.
PS_OUT="$(run_node psoff)" || die "the PowerShell check could not run"
printf '%s\n' "$PS_OUT"
passed=$((passed + $(grep -c '^ok ' <<< "$PS_OUT")))
failed=$((failed + $(grep -c '^FAIL ' <<< "$PS_OUT")))

# K-05 comparisons against the base.
K05_NAMES=(
  "K-05 base deny and ask entries kept unchanged"
  "K-05 hooks unchanged"
  "K-05 only scoped Bash deny entries added"
  "K-05 no allow, defaultMode or other key added"
  "K-05 settings.local.json not tracked"
  "K-05 change set limited to the allowed files"
)
inert=""
if [ -z "$BASE_GIVEN" ] && grep -q 'gh run rerun' <<< "$BASE_JSON"; then inert=1; fi

if [ -n "$inert" ]; then
  for name in "${K05_NAMES[@]}"; do
    echo "skip $name — the base already holds the new rules (task merged); re-run with --base <merge>^1 --head <merge>^2"
  done
else
  K05_OUT="$(run_node k05)" || die "the base comparison could not run"
  printf '%s\n' "$K05_OUT"
  passed=$((passed + $(grep -c '^ok ' <<< "$K05_OUT")))
  failed=$((failed + $(grep -c '^FAIL ' <<< "$K05_OUT")))

  if [ -z "$HEAD_REF" ]; then
    tracked_local="$(git ls-files -- "$LOCAL_SETTINGS")"
    changed="$( { git diff --name-only --no-renames "$MB"; git ls-files --others --exclude-standard; } | sort -u)"
  else
    tracked_local="$(git ls-tree --name-only "$HEAD_REF" -- "$LOCAL_SETTINGS")"
    changed="$(git diff --name-only --no-renames "$MB" "$HEAD_REF" | sort -u)"
  fi
  if [ -z "$tracked_local" ]; then
    echo "ok   K-05 settings.local.json not tracked"; passed=$((passed + 1))
  else
    echo "FAIL K-05 settings.local.json not tracked — $LOCAL_SETTINGS is tracked"; failed=$((failed + 1))
  fi

  outside=""
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    case "$path" in
      "$SETTINGS" | tests/doc-checks/EKO-1-18.sh | docs/PLAN.md | docs/cost-register/*) ;;
      *) outside="$outside $path" ;;
    esac
  done <<< "$changed"
  if [ -z "$changed" ]; then
    echo "FAIL K-05 change set limited to the allowed files — the change set is empty against merge base $MB; the comparison would prove nothing (give the base the task branched from)"
    failed=$((failed + 1))
  elif [ -n "$outside" ]; then
    echo "FAIL K-05 change set limited to the allowed files — outside the allowed set:$outside"
    failed=$((failed + 1))
  else
    echo "ok   K-05 change set limited to the allowed files — $(wc -l <<< "$changed" | tr -d ' ') paths against merge base ${MB:0:7}"
    passed=$((passed + 1))
  fi
fi

echo "EKO-1-18 checks: $passed passed, $failed failed (settings: ${HEAD_REF:-working tree}; base: ${MB:0:7}; task base ${TASK_BASE:0:7})"
[ "$failed" -eq 0 ]
