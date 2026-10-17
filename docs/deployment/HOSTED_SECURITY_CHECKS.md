# Hosted deployment security verification

Verification of the security properties of the live Vercel + Railway + Neon
deployment. Every result was observed against the running services, not
inferred from configuration.

Scope: assessor session handling, CSRF, private evidence storage and
serving, worker capability tokens, report signing, transport, and secret
management. Companion documents: `VERCEL_RAILWAY_NEON.md` (what is
deployed), `HOSTED_E2E_REPORT.md` (functional results).

## 1. Transport

| Check | Result | Evidence |
|---|---|---|
| Dashboard served over HTTPS | PASS | `https://parakh-dashboard-five.vercel.app` → 200 |
| API served over HTTPS | PASS | `https://api-production-c626.up.railway.app/health` → 200 |
| Database connection uses TLS | PASS | Neon connection string carries `sslmode=require` (and `channel_binding=require`) |
| Object storage over HTTPS | PASS | `https://{branch}.storage.c-4.ap-southeast-1.aws.neon.tech` |
| Android release forbids cleartext | PASS | merged manifest: `usesCleartextTraffic=false` + a `networkSecurityConfig`; `verifyReleaseForbidsCleartextTraffic` passes |

No plain-HTTP path exists anywhere in the hosted deployment.

## 2. Assessor session cookies

Observed in a real Chromium against the live deployment. The whole point of
the same-origin `/api` rewrite was to achieve this **without** weakening any
cookie attribute:

| Check | Result | Observed |
|---|---|---|
| Session cookie set at login | PASS | `access_token`, `csrf_token` |
| Session cookie is **HttpOnly** | PASS | `access_token` httpOnly |
| Session cookie is **Secure** | PASS | `secure=true` |
| Session cookie is **SameSite=Lax** — not downgraded to `None` | PASS | `sameSite=Lax` |
| Cookie is **host-only** (no shared parent domain) | PASS | `domain=parakh-dashboard-five.vercel.app`, no leading dot |
| HttpOnly cookie **invisible to JavaScript** | PASS | `document.cookie` contained only `csrf_token=…` |
| CSRF cookie readable for double-submit | PASS | `csrf_token` httpOnly=false |
| Authenticated request with the cookie alone | PASS | `GET /auth/me` → 200 |
| Logout clears the session | PASS | 200, then `GET /auth/me` → **401** |

`COOKIE_DOMAIN` is deliberately left **unset**, so cookies are host-only —
correct here because the dashboard and API share one browser origin through
the rewrite. No token was moved to `localStorage`.

## 3. CSRF

PARAKH uses double-submit: a readable `csrf_token` cookie must be echoed in
an `X-CSRF-Token` header on mutating requests. Enforcement lives in
`get_current_user` (`server/app/auth.py`), so it covers every endpoint that
depends on it.

| Check | Result | Observed |
|---|---|---|
| State-changing request **without** the CSRF header is rejected | PASS | `POST /assessments/{id}/start-review` → **403** |
| The same request **with** the header is not CSRF-rejected | PASS | → 409 (a legitimate state conflict, not 403) |
| Session survives a rejected CSRF attempt | PASS | `GET /auth/me` → 200 afterwards |
| Logout with the header succeeds | PASS | 200 |

CSRF was **not** disabled, globally or per-route, to make the deployment
work.

### One documented exception, pre-existing

`POST /auth/logout` takes no `get_current_user` dependency — it only clears
cookies (`server/app/routers/auth.py`) — so it is CSRF-free **by design**.
A forged logout reveals nothing and changes no data; the worst outcome is an
unwanted sign-out. This is P2.2 behaviour, unchanged by this deployment, and
is called out because an initial version of the hosted browser test
mistakenly used this endpoint as its CSRF probe and so appeared to show CSRF
was unenforced. Re-probing a genuinely protected endpoint showed enforcement
is correct.

## 4. Private evidence

| Check | Result | Observed |
|---|---|---|
| Bucket is private, not public-read | PASS | created `private`; `neonctl buckets list` → `access_level: private` |
| **Anonymous GET of a stored object is refused** | PASS | direct bucket URL → **HTTP 403** |
| Evidence requires a valid session | PASS | bogus token → **401** |
| Cross-assessment evidence access refused | PASS | smoke test step 13 (another assessment's worker token → 401/404) |
| Worker capability token cannot read the audit log | PASS | smoke test step 15 |
| Private responses are not shared-cacheable | PASS | `Cache-Control: private, no-store` from the API **and** a `vercel.json` header rule for `/api/*` |
| No permanent public object URL is ever issued | PASS | by design — see below |

**Evidence is proxied, never redirected to a presigned URL.** A presigned
URL is a bearer credential in a query string: it would bypass
`routers/evidence.py`'s authorization check entirely, land in browser
history, `Referer` headers and access logs, and remain valid for its whole
TTL regardless of whether the assessor still has access to the assessment.
The ranged proxy in `routers/evidence.py` keeps every request subject to the
same unchanged authorization model as the local backend.

## 5. Integrity

| Check | Result | Observed |
|---|---|---|
| Server independently re-computes evidence SHA-256 | PASS | never trusts the client value; mismatch → 409 (smoke step 8) |
| Declared byte count enforced | PASS | size mismatch → 409 |
| Manifest ECDSA signature verified over the exact device bytes | PASS | smoke steps 5–6 |
| Tampered manifest rejected | PASS | smoke step 8 |
| Evidence cross-checked against the signed manifest | PASS | sha256 + byte count + task binding |
| Stored object re-hashed after the fact by the worker | PASS | `verify_evidence` × 4 succeeded against the Neon bucket |
| Bucket-side corruption detected | PASS | `test_corrupted_object_is_caught_by_sha256` |
| Chunk replay handled idempotently | PASS | replay of `next_chunk_index-1` is a no-op success |
| Out-of-order chunk rejected | PASS | 409 |
| Interrupted upload resumes without loss | PASS | verified against the live bucket |
| Abandoned upload leaves no orphaned objects | PASS | `delete()` clears staging |

## 6. Report signing

| Check | Result | Observed |
|---|---|---|
| Signed PDF is produced and stored privately | PASS | 42 447 B, magic `%PDF-` |
| Original signed bytes returned on download | PASS | byte-identical via the proxy |
| Public verification succeeds | PASS | `/verify/{report_id}` → 200 unauthenticated |
| A tampered copy fails verification | PASS | smoke step 22 (offline `tools/verify_report.py`) |
| Public verify page exposes no secrets | PASS | rendered page scanned for credential-shaped text — none |
| Signing key is **stable** across redeploys | PASS | generated once; the env builder explicitly reuses it rather than regenerating |

> `REPORT_SIGNING_PRIVATE_KEY` must never be rotated casually: P7 stores a
> detached Ed25519 signature per report, so replacing the key invalidates
> every existing signature unless the retired public key is first moved into
> `REPORT_SIGNING_KEY_HISTORY`.

## 7. Secret management

| Check | Result |
|---|---|
| No secret is committed to git | PASS — `.env`, `.env.deploy`, `.vercel`, `local.properties` all gitignored; `git status` clean of them |
| Secrets pushed to Railway without touching a shell history or process list | PASS — `railway variable set --stdin KEY` reads the value from stdin |
| Operator secrets stored with restrictive permissions | PASS — `.env.deploy` is mode `600` |
| `.env.deploy` excluded from the Docker build context | PASS — added to `.dockerignore` |
| Storage credentials least-privilege | PASS — scoped `storage:read` + `storage:write` only (no `ai_gateway:invoke`, no `functions:invoke`) |
| No debug credential or auth bypass in the hosted config | PASS — `DEV_ASSESSOR_EMAIL`/`PASSWORD` unset; assessors created only via `provision_assessor` |
| No test-only route enabled in production | PASS — no debug router exists; Android release has every `*_TEST_ONLY_*` flag `false` |
| No demo seeding against the deployment | PASS — `app.seed` never run on either Neon branch; pack import only |

### Two credential-handling incidents during this deployment

Recorded in full because both involved real credentials reaching a place
they should not have:

1. **Neon printed the new project's full connection URI, including the
   database password, to stdout** when the project was created — and that
   landed in the session transcript. The `neondb_owner` password was
   immediately **reset** via the Neon API, invalidating the exposed value.
   The replacement was written straight to the gitignored `.env.deploy` and
   never displayed.
2. **An error path in a credential-provisioning script printed a storage
   credential's `api_token` and `s3_secret_access_key`** when its JSON parse
   failed. That credential (`nak_live_faa1a5…`) was **revoked**, as were the
   duplicates a retry loop had created. Confirmed revoked via
   `neonctl credentials list` (`revoked_at` set on every one). The script was
   rewritten so raw CLI output can never reach stdout — only field names,
   counts and truncated token ids are ever printed.

Active credentials at the end of the deployment are only those never
displayed anywhere.

## 8. Android release hardening

All checks are the repository's own Gradle verification tasks, run against
the release build configured for the real Railway endpoint.

| Check | Result |
|---|---|
| `verifyReleaseForbidsCleartextTraffic` | PASS |
| `verifyP6TestOnlySyncOverrideDisabledInRelease` | PASS |
| `verifyP6SyncEndpointOverrideAbsentFromRelease` | PASS |
| `verifyP4TestCeilingDisabledInRelease` | PASS |
| `verifyP5DebugFeaturesDisabledInRelease` | PASS |
| `verifyP5DebugExportAbsentFromRelease` | PASS |
| `verifyNoGalleryImportPath` | PASS |
| `verifyExpectedNetworkPermissions` | PASS |
| `verifyMergedManifestHasExpectedNetworkPermissions` | PASS |
| Release endpoint is the real HTTPS API, not the placeholder | PASS — `https://api-production-c626.up.railway.app` |
| No runtime endpoint override compiled into release | PASS — `P6_TEST_ONLY_SYNC_ENDPOINT_OVERRIDE_ENABLED=false` |
| TLS verification not disabled anywhere | PASS — no custom `TrustManager`/`HostnameVerifier`; cleartext forbidden unconditionally |

### Signing — NOT release-signed

The release APK is signed with the **Android debug key**:

```
Signer #1 certificate DN: C=US, O=Android, CN=Android Debug
SHA-256: 060109bd61004a28dea5b879349f21e19e6e3699eb6ba87c53301051642964e6
Verified using v2 scheme (APK Signature Scheme v2): true
```

This is the build's own documented, loudly-warned fallback when
`RELEASE_STORE_FILE` / `RELEASE_STORE_PASSWORD` / `RELEASE_KEY_ALIAS` /
`RELEASE_KEY_PASSWORD` are absent — and no keystore or signing material
exists on this machine or in the repository. The APK is therefore
**installable for testing but must not be distributed**.

No replacement keystore was generated: creating a distribution key is an
owner decision (and generating one carelessly would permanently break
updates to any already-signed release). To produce a genuinely
release-signed APK, supply the four properties as shown in
`VERCEL_RAILWAY_NEON.md` §7, and back the keystore up before using it.

## 9. Residual risks

* **Neon Object Storage is beta.** It behaved correctly throughout, but a
  beta dependency carries availability and API-stability risk.
* **The deployed backend points at the Neon `staging` branch.** Suitable for
  testing; switch to `main` before real assessments (six variables).
* **Railway trial expires 30 days from issue.** Not a security issue, but an
  availability one — see `VERCEL_RAILWAY_NEON.md` §6.
* **No release-signed APK**, as above.
* **Physical Android-to-cloud evidence capture is unverified** — see
  `HOSTED_E2E_REPORT.md`. Automated instrumented tests are not a substitute
  for a real worker capturing real evidence on a real site.
* Session expiry behaviour under a long-idle Neon compute was not
  specifically tested; the first request after suspension is slow but
  succeeded in every observed case.
