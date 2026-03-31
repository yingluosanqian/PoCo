# Commit Conventions

This document defines the commit message format for PoCo.

## Required Format

Use this exact structure:

`[type] summary`

Examples:

- `[feat] add cursor agent provider support`
- `[fix] adjust reply card state colors`
- `[refactor] split feishu card action handlers`
- `[docs] update tui architecture`

## Allowed `type` Values

Use one of these common types:

- `feat`: new user-facing capability
- `fix`: bug fix or behavior correction
- `refactor`: code structure improvement without intended behavior change
- `docs`: documentation-only changes
- `version`: version bump or release metadata
- `upd`: small update aligned with existing repository history

## Writing Rules

- Keep `summary` short and clear.
- Use lowercase words in the summary when possible.
- Focus on intent (why) more than file-by-file details.
- Avoid vague summaries like `update code` or `fix stuff`.

## Scope Guidance

- One commit should represent one coherent change.
- If a change mixes unrelated concerns, split it into multiple commits.
- If behavior changes and refactor are both included, prefer separate commits.

## Quick Checklist Before Commit

- Message follows `[type] summary`.
- `type` matches the nature of the change.
- Summary is specific enough for `git log --oneline`.
- Changes are logically grouped.

