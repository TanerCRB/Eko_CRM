---
name: zadanie
description: Drive one Eko_CRM Issue through the complete Ninefold process
type: prompt
disableModelInvocation: true
arguments:
  - issue
  - phase
---

Read and follow `.claude/commands/task.md` as the operational procedure for task `$issue`.

The optional starting phase is `$phase`. If it is empty, determine the phase from the Issue state, branches and open pull requests as described in the procedure.

Follow all human gates, hard stops, evidence requirements and repository rules. Write artifacts in English and reply to the human in the human's language.
