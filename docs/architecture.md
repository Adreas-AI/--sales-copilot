# Architecture notes

## Data model

| Table | Purpose |
|---|---|
| `leads` | The prospect: business facts, source, consent and preferences, pipeline stage, plus a copy of the latest score for fast filtering. `email` is unique (repeat inquiries merge); `(source, external_id)` is unique (webhook replays are no-ops). |
| `activities` | The timeline: inquiries, inbound/outbound emails, notes, calls, system events. `external_message_id` is unique, so duplicate mail deliveries are ignored. |
| `qualifications` | Every scoring run: factors, signals, missing info, AI adjustment and evidence, reasoning, warnings. History is kept. |
| `email_drafts` | Every generated email and its review trail. `UNIQUE(sequence_id, followup_step)`. |
| `followup_sequences` | One cadence run per lead, with a snapshot of the cadence. A partial unique index allows only one `active` sequence per lead. |
| `followup_tasks` | The concrete plan: one row per step, with `due_at` and `status`. `UNIQUE(sequence_id, step)`. |
| `suppressions` | Emails and domains never to contact. |
| `jobs` | The work queue. |

All timestamps are timezone-aware UTC (`UTCDateTime`), including on SQLite.

## Lifecycle of a demo request

1. `POST /intake/forms/demo` creates the `lead` and an `inquiry` activity, and enqueues `qualify_lead` (key `qualify:{lead}:intake`). All of this commits in one transaction.
2. The worker runs `qualify_lead`. It runs the rules plus the optional AI review, stores a `qualification`, and enqueues `prepare_initial_outreach` (key `initial-outreach:{lead}`).
3. `prepare_initial_outreach` goes through these checks in order:
   - If the lead prefers phone, cannot be emailed, or looks like a non-buyer, it is flagged for review and nothing else happens.
   - Otherwise a `demo_invitation` draft is created.
   - If the lead's temperature is in `FOLLOWUP_TEMPERATURES`, a sequence is created with tasks due at `created_at + 2d`, `+5d` and `+10d`.
4. On each tick, the worker enqueues `process_followup_task` for due tasks (key `followup-task:{task}`).
5. `process_followup_task` locks the task row and works through these steps:
   - It returns if the task is no longer `scheduled`.
   - It re-checks the stop conditions.
   - If an earlier draft is still awaiting review, the step is skipped.
   - Otherwise it creates the follow-up draft and completes the task.

   On the manual-review step it flags the lead and completes the sequence.

## Why each step is idempotent

| Step | Guard |
|---|---|
| Enqueue | unique `idempotency_key` |
| Qualify | adds a history row; re-running is harmless |
| Initial outreach | checks for an existing draft; `start_sequence` returns the active sequence if one exists; the partial unique index backs this up under races |
| Task processing | row lock + `status == scheduled` check; unique `(sequence_id, step)` on drafts |
| Job completion | `UPDATE … WHERE locked_by = me AND status = running`; a worker that lost its lease rolls back |

## Time

All code calls `app.core.clock.utcnow()`. Tests and `scripts/simulate_followups.py` freeze or advance it to run ten days of workflow in milliseconds. `scripts/seed_demo.py` uses it to replay a realistic two-week history through the real worker.
