---
description: Eko_CRM — drives one task through the Ninefold process, from Issue to PR, stopping at the human gates
---

# Task: {{args}}

You are driving **one** task through the Ninefold process, in Qwen Code.

## Arguments

`{{args}}` is the whole argument string. Split it yourself — this environment passes no
positional `$1`/`$2`:

- token 1 — the Issue, a full URL or `#N`. Required; if it is missing, ask and stop.
- token 2 — optional starting phase: `analysis` | `code` | `verification` | `pr` | `closure`.
  Without it, determine the phase from the Issue's state label, the branch and open PRs.

## Read first, in full, before any step

1. `.claude/commands/task.md` — the operational procedure. Every step, gate, check and script
   is defined there. This file adds nothing to it and takes nothing away.
2. `TEAM-CONTRACT.md` — roles, human gates, hard stops; governs over role files on discrepancy.
3. `AGENTS.md` — this repository's working agreement.
4. `process/sdlc-flow.md` — states and transitions.

On any discrepancy, those four win over this file.

## Substitutions for this environment

Everything else in the procedure runs unchanged.

**Roles run in general-purpose mode.** The ten roles in `agents/` are not registered subagent
types here. Follow `.claude/commands/task.md`, "How you call a role", fallback mode: call the
general-purpose agent and paste the full content of `agents/<role>.md` as the first part of the
prompt, ahead of the task context. Because this mode does not enforce the role's `tools`
declaration, restore the boundary mechanically: run `scripts/boundary-check.sh` around **every**
role call, with `--none` for the read-only roles. Record `"invocation": "general-purpose"` in
every cost-register row. Raising a role's model above the session's needs the human's consent.

**Worktree by hand, not by tool.** Create it with
`git worktree add ../Eko_CRM-<identifier> -b <identifier>-<slug>` from a shell. Do not use this
environment's own worktree tool — it creates `.qwen/worktrees/<slug>` inside the checkout, and the
procedure names both the location (`../Eko_CRM-<identifier>`) and the reason to keep out of an
agent-configuration directory: quality tools that do not scan it hand back a green check that
checked nothing.

**Scripts through Git Bash.** The shell here is `cmd.exe`; run every process script as
`bash scripts/<name>.sh`. Read exit 2 as "the check could not run", never as "clean".

**Journal and cost numbers.** Read `.task/journal.md` yourself as the first act of step 0 on a
resumed task, whether or not the SessionStart hook is registered in `.qwen/settings.json`. Write
every cost-register row as `"measured": "by hand"`, with `"no data"` in the measured columns and
the reason `"cost-capture.mjs cannot parse this environment's transcript"` — never a guessed
number. Measured on 0.26.8: entries here carry usage under `usageMetadata` in this environment's
own field names, with no `message.id` to deduplicate on, so the hook returns `"no data"`. Do not
substitute the numbers from `~/.qwen/usage/` — that ledger keys its rows by session and carries no
agent identifier, while the canonical mechanism looks a record up by the agent id returned at
launch, so no row there can be attributed to one role call.

**No TODO tool.** Keep the one-entry-per-step list in `.task/journal.md` instead.

**Compressed conversation.** A compressed-communication mode is available here. Turn it on for
messages to the human in this window only. Artifacts — Issues, comments, commit messages, PR
descriptions, documentation, code comments — stay in full, careful English. Reply to the human in
the language they write in.

**Gates 1, 2 and 3 belong to the human.** Prepare the material, apply `waiting-on-human`,
unassign yourself, and stop. Never remove that label yourself, never merge a pull request, never
raise a status in a register.
