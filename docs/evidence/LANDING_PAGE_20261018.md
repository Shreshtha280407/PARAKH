# Parakh landing page — review

Implemented locally on top of `2e4602a` (`Updated frontend`). Ready for your review and separate commit. Preview: **http://localhost:18177/**.

## Experience

- **“Skill, made visible.”** A warm paper, walnut, and brass introduction using the dashboard’s existing Fraunces, Noto Sans, and JetBrains Mono fonts and original Parakh emblem.
- **A floating evidence folio.** Pointer tilt, layered paper, orbit lines, a brass seal, and restrained ambient motion introduce the evidence-first idea.
- **Capture → Preserve → Recognise.** A sticky, scroll-driven desktop sequence transitions from an illustrated worker phone to sealed evidence and a signed report. Chapter controls also work directly; on phones, they switch the scene and accompanying explanation together.
- **An interactive task explorer.** Five individually drawn schematics cover safety, tools, wiring, lighting, and panels. Each selection shows readable task details, a secondary standards reference, and its real final-evidence budget: **15 / 20 / 30 / 25 / 30 MB**.
- **A clear explanation of trust.** Evidence-quality guidance, human scoring, versioned rubrics, safety criteria, revision history, integrity checks, and public report verification.
- **Working entry points.** Enter dashboard, the header dashboard link, and Begin a review all open the existing assessor queue. The footer links to the existing report-verification page.

## Content grounding

Reviewed the supplied `KaushalPramaan_MVP_Master_Plan.pdf`, especially the scope, task pack, evidence lifecycle, human review, signed reports, and AI-assistance sections. Cross-checked the implemented scope against the repository README, the current dashboard, assessment APIs, Android capture/sealing/assistance flow, and `packs/ae-con-q0602/{tasks,qp}.json`.

The page presents the **Assistant Electrician pilot, CON/Q0602 v4.0, NSQF Level 3**. It describes assessor recommendations and verifiable signed reports. The workflow graphics are labelled illustrations. Agreement-study results, automated competence verdicts, additional live trades, and awarding-body integrations are not advertised.

## Motion, access, and performance

- Motion follows the operating system’s reduced-motion preference, with an explicit pause/enable control.
- Decorative loops pause outside the viewport and when the browser tab is hidden; inactive cinematic scenes also pause their loops.
- Scroll and pointer updates use animation frames and DOM refs rather than a React render on every event.
- Native scrolling, keyboard task navigation, visible focus, a skip-to-content link, and labelled controls remain available.
- Landing JavaScript and CSS load in a separate route chunk. The production build adds approximately **9.93 kB JavaScript + 9.39 kB CSS gzipped** for the landing route. These are bundle sizes, not measured mobile performance results.
- Existing local fonts and logo are reused; the display font is preloaded. No new dependencies, remote fonts, video downloads, or external animation services.

## Verification

**17 browser checks passed**, using the existing local dashboard and dedicated local test API. See [verification receipt](LANDING_PAGE_20261018/verification.json).

| Area | Result |
| --- | --- |
| Landing, local fonts, unique IDs, original logo | Passed |
| Three section-navigation buttons | Passed |
| Scroll-driven chapters and direct chapter controls | Passed |
| Five distinct task illustrations and real pack budgets | Passed |
| Arrow keys, Home/End, focus, and tab-panel associations | Passed |
| Pause/enable, reduced motion, offscreen animation suspension | Passed |
| Responsive layout at 320, 390, 640, 768, 900, 1024, 1440, 1920 px | Passed; no horizontal overflow |
| Phone workflow scene and explanatory text | Passed |
| Back to top and keyboard skip-to-content | Passed |
| Enter → queue → successful local API read | Passed |
| Header/closing entry links and public verification link | Passed |
| Repeated route changes, JavaScript and network checks | Passed; zero JavaScript errors or failed requests |

`npm run build` passed. `npm run lint` completed with zero errors and the existing nine advisory warnings in other files. `git diff --check` passed. Browser verification was read-only; no candidate assessment or decision was created or changed.

## Screenshots

| Desktop | Phone |
| --- | --- |
| [Hero](LANDING_PAGE_20261018/desktop-hero.jpg) | [Hero](LANDING_PAGE_20261018/phone-hero.jpg) |
| [Seal and sync](LANDING_PAGE_20261018/desktop-seal-and-sync.jpg) | [Workflow](LANDING_PAGE_20261018/phone-workflow.jpg) |
| [Human review](LANDING_PAGE_20261018/desktop-human-review.jpg) | |
| [Task explorer](LANDING_PAGE_20261018/desktop-task-explorer.jpg) | |
| [Trust](LANDING_PAGE_20261018/desktop-trust.jpg) | |
| [Closing and footer](LANDING_PAGE_20261018/desktop-closing.jpg) | |

## Delivery

Source changes are limited to the dashboard entry page, its dedicated stylesheet, route loading, and HTML metadata/font preload. Dashboard workflows, backend, Android app, and original logo asset are unchanged. No phone installation is needed for this update.

**No commit, push, or deployment was performed.** The hosted dashboard receives this landing page through your normal release workflow after you push the commits.
