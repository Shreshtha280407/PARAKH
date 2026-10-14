# P6 physical-device run — 2026-10-14

Executed the remaining interruption, force-stop, receipt/cleanup and assessor-review steps
on the user's USB-connected OnePlus 13R (CPH2691), using the existing sealed practice draft.
The installed app reported `0.6.0-p6`. Repository HEAD was
`21d3911a4752bf6ff86dff6318b72b648f2b81e7` on
`feature/p6-resumable-sync-review`, with pre-existing working-tree changes.

| Check | Observed result |
| --- | --- |
| Group 3 — interrupted upload and force-stop | PASS: five rapid off/on cycles, a dropped acknowledgement after a committed chunk, force-stop while incomplete, and resume of the original session |
| Group 5 — receipt and cleanup of this draft | PASS: evidence vault retained during the interruption and removed after the verified receipt; phone displayed submission success |
| Group 5 — whole-app plaintext sweep | Finding: two JPEGs and a manifest from an older explicit P5 debug verification export remain |
| Group 6 — dashboard playback, scoring and audit | PASS: protected video playback, 71 saved criteria with remarks, and 72 assessor audit entries |

This record covers the requested remaining steps. Other physical-device gate groups were
not rerun, and this record does not close the entire P6 manual gate.

## Assessment and uploaded file

- Server assessment: **10**; worker: **11**, displayed as `Worker`, device worker ID
  `KP-39406001`. The bootstrap does not populate the server's phone field, so the draft was
  identified by its signed client UUID rather than a phone-number search.
- Client assessment: `430713ef-a547-4d8e-a164-c2dd3b60482b`.
- Revision: `fa273812-886c-40fe-ae96-1ede2e4f2f86`.
- Evidence: **7**, T1 video, client item `f7e3b9e0-0892-42af-b73d-28f73d56deac`.
- Actual file size: **15,379,488 bytes** (14.67 MiB), **15 chunks**. Final chunk: 699,424 bytes.
- Actual video metadata: 1280 × 720, 8,765 ms; the browser displayed the portrait rotation
  and a duration of approximately 8.77 seconds. This draft's capture was shorter than the
  runbook's estimated 60 seconds, while still supplying the required large chunked file.
- SHA-256, independently recomputed from server storage and matched to the evidence row,
  upload receipt and signed manifest:
  `17fc3bbcaa57bb5b6c7cf2bee450d973f726a02c6b139aae7884e91609b089ad`.

## Interruption and recovery

The pre-test screen showed airplane mode ON, `0 of 2 items done`, and both items Queued.
The encrypted video vault file was 15,439,848 bytes before upload.

The USB tunnel was temporarily forwarded through a local test proxy on port 18001. The
proxy delayed chunk acknowledgements by two seconds to create a reproducible interruption
window. During airplane-mode-ON intervals it cut the connection, because the USB loopback
path can otherwise remain reachable despite airplane mode. It forwarded the app's normal
requests to the unchanged API on port 18000 and did not log credentials or media bodies.

Observed timeline (IST):

1. **12:41:36** — tapped Sync now while offline, then disabled airplane mode.
2. **12:41:41** — server committed video chunk 0; its acknowledgement was deliberately
   dropped. Manifest session 14 was already complete.
3. **12:41:42–12:41:46** — completed five additional rapid off/on cycles, verifying each
   airplane-mode setting. There were 13 transitions including initial connectivity changes
   and the final restoration; five were the requested rapid complete off/on cycles.
4. **12:41:49** — force-stopped PARAKH with airplane mode ON. The screen showed
   `1 of 2 items done`, Manifest Synced, and T1 `Retrying… (attempt 1)`.
5. Server verification after force-stop showed assessment 10 still `draft`, manifest
   session 14 `completed` at 2,087/2,087 bytes, and evidence session 15 `open` at
   1,048,576/15,379,488 bytes. The encrypted evidence file remained on the phone.
6. Relaunch restored the Practice tasks screen with the same T1 item. Navigated through
   Preview and submit back to Review and seal; the retry state survived.
7. **12:43:28** — restored connectivity and tapped Sync now. WorkManager retained the
   pending job and its existing exponential backoff.
8. **12:52:22** — automatic retry recovered session **15** via the idempotent upload-open
   endpoint and continued with chunk **1**, then chunks 2–14. No second evidence session
   was created, and chunk 0 was not sent again.
9. **12:52:26** — evidence completed and the server accepted submission. The phone displayed
   **“Synced and submitted for assessor review.”**

Elapsed time from the initial sync tap to submission: **650.78 seconds (10 min 51 sec)**.
Elapsed time after connectivity was restored: **538.68 seconds (8 min 59 sec)**.
Most of this was WorkManager backoff: the scheduling database recorded attempt count 7,
a 10-second exponential base and a next-run time of 12:52:21.948 IST. The five rapid toggles
did not each produce a distinct upload attempt; the proxy trace proves one lost-acknowledgement
failure followed by successful recovery after force-stop.

Independent server checks before starting review confirmed:

- Assessment 10 `submitted` at `2026-10-14T07:22:26.812446+00:00`.
- Exactly two completed upload sessions: one manifest and one evidence session; received
  bytes equal claimed bytes and actual storage size for each.
- Exactly one evidence row and one complete device manifest.
- Contiguous evidence chunk indexes 0–14, zero duplicate chunk rows and zero orphan rows.
- Evidence SHA-256 matches the signed manifest; the manifest's ECDSA signature was verified
  again from its stored envelope. Manifest canonical SHA-256:
  `4a44130df962e1fb766dbc0ff53ac34956116364335c52e06af80e3ea2012152`.
- Background metadata and thumbnail jobs completed.

## Receipt and local cleanup

The manifest vault disappeared after its own receipt, while the evidence vault remained
through the interruption and force-stop. After final submission, the current assessment's
vault tree was absent. No raw video, optimisation copy or streaming plaintext file for this
draft appeared in the observed app-private file listings.

The whole-app `find files -type f` sweep still found the following **older debug exports**
for client assessment `faa52e78-66af-4408-b7e5-48d0ec1ddee7` (server assessment 6, already
submitted before this run):

```text
files/p5_debug_export/faa52e78-66af-4408-b7e5-48d0ec1ddee7/1791915704861/manifest_package.json
files/p5_debug_export/faa52e78-66af-4408-b7e5-48d0ec1ddee7/1791915704861/e4d2413d-e551-457d-81a7-fc463bfa894b.jpg
files/p5_debug_export/faa52e78-66af-4408-b7e5-48d0ec1ddee7/1791915704861/85b63003-c8a9-41f4-8a6a-1d085cf5f8e2.jpg
```

These existed before this run and were preserved. Source inspection confirms that the
P5 debug export is explicitly decrypted, requires explicit cleanup, and has a separate
cleanup action. The current draft's normal receipt cleanup succeeded, while the broader
claim that the entire debug installation contains no plaintext is false.

The runbook's deletion timing should distinguish the artifacts: raw capture plaintext is
removed during sealing, and P6 deletes each encrypted vault artifact after verifying that
artifact's server receipt. The observed interrupted video vault remained available until
the evidence receipt was confirmed.

## Assessor review

Logged in through the dashboard as `Demo Assessor`, opened assessment 10 from the queue,
and played its protected video successfully. The footage shows a room and desk rather than
the task demonstrations; T2–T5 contain no evidence.

Started review and saved **all 71 rubric criteria** through the dashboard controls, each
with level 0, `NOT_OBSERVABLE` and an explicit P6 technical-practice remark. T1 remarks
record that the footage does not demonstrate the criterion; T2–T5 remarks identify missing
task evidence. Reloaded server data confirmed all 71 remarks persisted.

The dashboard's audit-log section and a separate database query confirmed **one
`review_started` entry and 71 `scored` entries** attributed to the assessor. Final assessment
status is **`in_review`**, with assessor ID 1. The earlier successful submission remains
recorded in `submitted_at` and the worker `submitted` audit entry.

## Service corrections and final state

- Restarted the stopped containers without removing their database or evidence volumes.
  Rebuilt the stale migration image after it failed to locate revision `31f43e2b42be`.
- Rebuilt the dashboard using the root `.env`; the first build had embedded API port 8000
  instead of the running host port 18000. Login succeeded after correction. The reproducible
  command is `docker compose --env-file .env -f infra/docker-compose.yml up -d --build`.
- Observed that Sync now uses `ExistingWorkPolicy.KEEP` and does not shorten an existing
  retry backoff. Relaunch returned to Practice tasks, requiring navigation back to review.
- Restored `adb reverse tcp:8000 tcp:18000`, stopped the temporary proxy and left airplane
  mode OFF. The phone remained on its successful sync screen. API, database and dashboard
  health checks passed; the worker remained running.

Durable text/JSON evidence is in [evidence/P6-2026-10-14](evidence/P6-2026-10-14).
Additional local UI dumps, screenshots and playback frames are in
`/tmp/parakh-p6-20261014/`. Credentials, media bodies and scheduling databases were excluded
from the durable evidence copies. No commit or push was performed during this run.
