# Copilot v9 checkpoint — November 17, 2026

Only the formal single `orchestrator-chatbot` v9 path remains, using `gpt-6-luna`.
The local prompt/tool/output definition must stay identical to the saved v9 definition.
Cloud versions 1–8 and `copilot-chatbot` v1 remain untouched. Private bindings and personal
resume/report data are excluded from Git. The user performs commit and push manually.

## Supported behavior

- Conversation, supplied-text rewriting and follow-ups in the existing dashboard.
- Reads of the current user's confirmed technical skills, education, work/research
  experience and projects, plus existing skill-gap reports for the selected direction.
- No profile/plan/resume writes, new analyses, recomputed scores, recommendations or specialists.
- Database reads use private PostgreSQL READ ONLY transactions and fixed ownership queries;
  existing local report files are read without worker startup, recovery or modification.
- Existing version-1 browser history, drafts, old labels and source entries remain readable.
  New messages use authenticated `foundry_chat`; legacy records are not model evidence.

## Retired implementation

Removed the unused understanding-Agent prompt/schema/settings, old account-service reader,
intermediate resume GET/DTO, unused section helper, v8 execution branch and product demo.
Necessary test fixtures remain test-only. The v9 prompt was moved unchanged to Instructions.md.
The explicit enable flag remains; false disables Copilot rather than selecting another mode.
Full earlier experiment notes are archived locally outside this repository.

The earlier two-Agent experiment took roughly 7–9 seconds for short requests and motivated
single-Agent iteration. This is historical context, not a current latency benchmark.

## Confirmed regression and repair

A real dashboard report request returned 502 with `source_ids: too_long`: per-skill citations
exceeded the eight-ID output limit. Reports now issue one document source; together with five
possible resume-section sources a turn offers at most six valid IDs. Full report values are
unchanged, and unknown/duplicate/missing sources still fail closed. A 23-skill regression
covers this boundary. Diagnostics omit content, credentials and identifiers.

## Account-switch repair

A stale tab could retain owner A while obtaining token B, then store B's reply in A's local
history. Account state now subscribes to shared login changes and ignores stale profile
loads/updates. Owner-bound requests check an atomic session token/user pair before send and
before accepting the returned JSON, reject mismatches, and do not sign out a newer account.
The private page subtree remounts on owner change and old shared GETs are invalidated.
A backend 401 now returns the existing sign-in error without automatically deleting the shared
Supabase session or redirecting; explicit Sign out remains available. The installed SDK cannot
conditionally sign out only the failed token, so an old request must not sign out a new login.
Same-user token refresh preserves conversation/draft. Existing browser history is not deleted.

## Verification

- Cleanup offline results: pending final combined run.
- Before cleanup: 112 backend and 43 Copilot frontend checks passed; type checking/lint passed.
- Previous v9 cloud checks with fictional readers succeeded for greeting/resume/report paths;
  the larger 23-skill report check succeeded after citation repair. No real personal data was
  used by these smoke checks. No cloud calls are needed for this cleanup.
- User-reported dashboard checks passed: greeting, repaired report lookup, saved skills,
  internship count and follow-up, and explicit refusal to save a requested Rust addition.

These observations do not independently verify every saved fact or establish a speed target.
Personal resume content is deliberately omitted from this record.

## Manual checks still open

- Read saved skills again after a refused addition to check requested text is not saved evidence.
- Switch career direction and verify matching resume/report or explicit missing-report behavior.
- Exercise two real tabs/accounts; check owner change, in-flight cancellation, separate history
  and same-account token refresh. Offline mocks cover the race, not a real browser session.
- Compare returned personal facts/scores and expanded Evidence with underlying saved records.

The assistant must not stage, commit, push or create a PR. The user decides when to submit.
