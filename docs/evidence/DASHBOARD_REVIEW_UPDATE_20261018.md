# Parakh dashboard review update — 18 October 2026

Implemented and live at **https://parakh-dashboard-five.vercel.app/**. The existing phone app uses the same API address and requires no update for these changes. Nothing has been committed or pushed.

## Completed decisions

After a successful password-confirmed action, a themed confirmation popup describes the result and automatically returns to the assessment queue after 2.4 seconds. **Back to queue** returns immediately.

- Positive sign-off: **Report signed successfully**.
- Signed negative recommendation: **Report signed — not yet qualified**.
- Other signed recommendations identify partial competency or missing evidence.
- Rejection: **Assessment marked not qualified**.
- Targeted evidence request: **Reassessment requested**, confirming the worker instructions were saved. This action records a request; it does not claim to create a signed PDF.

Failed passwords or failed server actions leave the review open with an error and do not display a success popup. The queue’s cached public entry updates only after the server confirms success. Signed rows show the actual final recommendation, including negative recommendations. The **Signed reports** filter includes signed reports of every outcome.

## Dashboard speed

The old screen waited for seven private requests, took assessment-row locks on read-only account requests, and performed repeated database queries for individual scores and evidence items. The API was also running in the US while its existing database is in Singapore.

The initial private review now uses one authorized workspace request. Audit/history loads when its tab opens and is reused. Read-only account requests no longer lock assessment rows; consequential actions retain their existing locking, version checks and password confirmation. Score, report and sync queries use batch loading. The public queue displays its cached rows immediately while fetching fresh data. Inactive scoring and history sections retain their state without rendering their full contents. The unused private-dashboard bundle loads separately.

The existing API now runs as **one replica in Singapore**, matching the database region. The API domain and data stores are unchanged; no new database or schema migration was needed. Railway supports changing the service region without changing its domain; see its [region documentation](https://docs.railway.com/deployments/regions). The desired region is recorded in `infra/hosting-target.json`.

| Measurement | Before | After |
| --- | --- | --- |
| Live initial private review, same existing assessment | 13.792 s, 13.136 s | 2.062 s, 1.657 s |
| Initial private HTTP requests | 7 | 1 |
| Live top navigation, click to selected page | — | 50–96 ms across desktop/mobile checks |
| Local history tab, with a deliberate 1.2 s network delay | — | 42 ms to selected tab and loading state |
| Local scoring tab | — | 219 ms |
| Local return to cached queue, with a deliberate 1.8 s network delay | — | 133 ms to visible rows |

These are real browser/API observations, not load-test percentiles. Full data and media transfer times still depend on network conditions. The initial-load comparison includes the history requests that blocked the old screen; the new screen defers those requests until needed.

## Scoring and readable names

Scoring is grouped into the **five evidence tasks**, with a saved/remaining count for each task. Only the selected task’s criteria are displayed. The pack contains **71 individual skill checks** across those five tasks; the underlying checks and scoring rules have been preserved.

Each criterion now leads with its actual skill description from the imported qualification pack. It includes what to look for, available marks, a clear performance-level selector, a readable evidence-status selector, the full selected level description, remarks and **Save score**. All four complete rubric anchors are available under **See all scoring levels**. Saved, unsaved and reopened criteria have distinct labels. Draft entries survive switching tasks and evidence tabs. **View task evidence** opens the matching evidence task.

Qualification names, task names and competency descriptions take priority throughout the review and queue. Qualification and criterion codes remain small secondary references. The competency breakdown displays skill-area names rather than leading with `CON/N…` codes.

## Revision history and reassessment requests

Revision history uses a numbered timeline with a current-version marker, status colours, timestamps and readable reopened-task chips. Reassessment requests use separate cards: amber for pending requests, green for fulfilled requests and muted styling for cancelled requests. Each request separates the reason from the worker’s capture instructions. The audit records and their contents are preserved.

## Verification

- **90 backend tests passed** against dedicated local PostgreSQL: assessor accounts, permissions, scoring, signing, sync protocol and concurrency. New checks confirm correct task/criterion metadata, protected bundle endpoints, batched queries and the absence of assessment write locks during account reads.
- **12 complete local browser checks passed**: account form, password errors, photos/video playback and seeking, score saving, draft preservation, positive signing, rejection, reassessment, popups, queue return and login/logout.
- **3 additional browser checks passed**: delayed-network responsiveness, cached queue return, and a signed negative recommendation with the correct queue outcome.
- **6 deployed verification checks passed**, with **zero browser errors**: workspace and lazy history, all task buttons, readable labels, persistent navigation, desktop/mobile layout and private response/session handling.
- Production build, lint and OpenAPI freshness checks passed; `git diff --check` is clean. Lint has advisory warnings and no errors.
- Live checks created one clearly named synthetic assessor account, then revoked its session. They created **zero candidate assessments** and changed **zero candidate decisions**. Screenshots below use isolated local test records.

## Review screenshots and deployment

- [Desktop scoring](DASHBOARD_REVIEW_UPDATE_20261018/scoring-desktop.png)
- [Mobile scoring](DASHBOARD_REVIEW_UPDATE_20261018/scoring-mobile.png)
- [Revision history and reassessment request](DASHBOARD_REVIEW_UPDATE_20261018/revision-and-reassessment.png)
- [Signed negative-outcome confirmation](DASHBOARD_REVIEW_UPDATE_20261018/signed-negative-confirmation.png)
- [Raw live measurements](DASHBOARD_REVIEW_UPDATE_20261018/live-performance.json)
- [Verification and artifact checksums](DASHBOARD_REVIEW_UPDATE_20261018/verification.json)

Dashboard production deployment: `dpl_7d1N2frwe8zfE3eGw1u3pj9WZFBf` — **Ready**. API deployment: `96711d76-3854-4e0d-a06f-74f1d08423ee` — **Success**, one healthy replica. These are uncommitted review builds based on `df6c575383afa1c61b654691d4f382ab30e1570f`; the API source-content checksum is captured separately in the evidence receipt. Commit and push remain for your manual review.
