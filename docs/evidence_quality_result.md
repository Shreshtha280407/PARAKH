# Evidence quality result -- stable integration contract (no model)

This document defines a contract for a *future* automated evidence-quality
check (blur/framing/audibility detection, or similar) -- **no such model
exists, is trained, or runs anywhere in this codebase.** This phase
(P2.2) deliberately stops at defining the shape so a future phase can slot
a real check in without changing any API consumer.

## Why this exists now, with nothing behind it

The master plan anticipates an automated quality signal on uploaded
evidence (e.g. "this photo is too dark to assess"). Building that model is
explicitly out of scope here -- see `server/README.md` and the P2.2 task
list ("do not build/train a CV model"). What *is* in scope is making sure
that whenever such a check lands, it has an API shape to land into, so the
dashboard and worker app can be built today against a stable contract
rather than guessing at one later.

## The contract

Every `EvidenceItem` carries a `quality_check_status` column (see
`server/app/models.py`), one of:

| Status | Meaning |
|---|---|
| `not_run` | Default. No quality check has ever been attempted. This is the only value this phase ever actually produces. |
| `queued` | A quality-check job has been enqueued but not yet processed. (No code enqueues this job today -- reserved for the future worker handler.) |
| `completed` | A check ran and produced a result (shape TBD when that lands -- e.g. a score, flags, or free-text findings; deliberately not designed yet, so as not to lock in an untested shape). |
| `unavailable` | A check was attempted but could not produce a result (model unavailable, unsupported file, timeout) -- same "never block on this" philosophy as `thumbnail_status` (see `docs/gates/P2_2.md` section 5). |

`not_run` is a steady-state value, not a placeholder error -- an assessor
reviewing evidence today will always see `not_run`, and that is the
*correct*, honest value for a system with no quality-check model.

## What a future phase would add

- A `check_evidence_quality` job type (mirrors `generate_thumbnail`'s
  shape in `server/app/worker.py`): claimed, processed, graceful fallback
  to `unavailable` on failure, never raises for an expected non-match.
- Whatever result schema the actual model produces, stored however makes
  sense then (a new column, a new table -- undecided, because no model
  exists to size it against).
- A dashboard affordance surfacing the result next to the evidence
  viewer (`server/app/routers/evidence.py`) -- purely informational,
  never gating scoring or the assessor's decision (see
  `docs/evidence_status_model.md` and `schemas.COMPETENCY_PROFILE_DISCLAIMER`
  for why this product never lets an automated signal replace human
  judgement).

## What this is explicitly NOT

- Not a CV/AI model. Not a dependency on one. Nothing in `requirements.txt`
  implements or calls one.
- Not a gate on any workflow -- `quality_check_status` is never read by
  any router or validation path in this phase; it is pure, unused-but-
  reserved schema.
- Not evidence-status (axis 2, `evidence_status` on
  `AssessmentCriterionScore` -- DEMONSTRATED/NOT_OBSERVABLE/
  NOT_APPLICABLE_IN_MVP). That's a human assessor's judgement call, always.
  This document is about an orthogonal, hypothetical automated signal that
  might one day help a human notice a bad photo faster -- never about
  automating the judgement itself.
