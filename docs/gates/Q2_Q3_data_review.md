# Q2/Q3 initial visual review — not a frozen evaluation set

Protocol: `proxy-intake-v2`. Archive identity is in [the progress record](Q2_Q3_progress.md).
Private contact sheets/thumbnails are under the external dataset root's `review/` directory.
No model predictions were used for these observations. Reviewer: Codex direct visual review,
2026-10-14. These are initial observations; complete timestamp labels and final quality
truth are still pending. No held-out evaluation has run.

## Observed content and limitations

- Inspected a ten-photo category overview; pages 2 and 3 of all five photo categories;
  page 1 of Out_of_frame; and the five video category sheets (one initial frame per
  video in the video folders). Review covers representatives of every supplied quality
  category and both hand-folder labels. Full-resolution/questionable follow-up and
  complete hand timestamp review remain required.
- Repeated scenes include a grey table with a laptop/power strip/cables and a grey
  table with writing and an orange-edged stationery pouch. Many photographs/videos
  depict the same objects/backgrounds across quality categories. Filenames do not
  establish independent recording sessions. Grouping these conservatively is necessary
  before calibration/validation/holdout splits; no split is frozen.
- Some Blurry-labelled photographs show strong haze/low contrast as well as reduced
  detail. Some Motion_blurry photos still show sharp background detail and localized
  subject motion. Preserve original categories and review technical conditions as
  multilabel annotations; these observations do not establish per-file truth yet.
- Out_of_frame photographs show varied crops, sometimes a recognizable power strip,
  sometimes cables, sometimes hands or a pouch. The intended target/acceptable extent
  is unspecified. Hand presence and framing are demonstrably separate. No defensible
  generic semantic-framing rule has been established from luma/Laplacian/frame differences.
  The owner has been asked to choose scope or provide an observable target/context
  contract **before** framing implementation or a changed acceptance denominator.
- Video folder hand annotations cannot be used directly as ground truth: visibly
  present hands occur in several Hands_not_visible clips. For example
  `m-60e52dc7f0bd` visibly contains hands at its initial, middle and near-final review
  frames, and `m-cb0067b62af2` does too. `m-f0d3e8f0f933` includes hands with a
  severely blurred middle review frame. All evaluated timestamps need independent
  labels, with unjudgeable frames retained explicitly rather than scored as absent.
- Some preliminary Out_of_frame/Hands_not_visible frames show no hand; the exact
  timestamps and transition intervals still need full review. This does not establish
  enough independent negative clips in each future partition.

## Acceptance implications

Folder labels are retained as owner annotations. None has silently been promoted to
verified ground truth, rewritten to match predictions, removed from an evaluation
denominator or moved out of a holdout. No target detector, hand-to-framing substitution,
competence classifier or production capture-flow change has been implemented.

Required next decisions/data: the framing contract/scope, conservative capture-session
groups (owner information if available), and enough independent groups and both hand
classes for the eventual frozen evaluation protocol. Three-phone collection is not
proved by filenames or model names. Proxy engineering results will remain distinct
from real-trade field confirmation in Q4/P8.

## Subsequent decisions and completed hand review (2026-10-14)

The observations above are historical initial review. The owner explicitly approved revised
Q2 technical exposure/blur/temporal camera-motion acceptance; semantic task-target framing
is unsupported, not implemented or promised for Q4/P8. Every original Out_of_frame label
is retained; missing a semantic target alone does not make technical evidence bad.

All 40 unique clips were subsequently reviewed at 497 requested 1s timestamps before any
model inference: present 378, absent 97, unjudgeable 22. Fifteen original not-visible clips
contain present samples. Versioned independent review/provenance and original/corrected
labels are in `ml/hands/data/`. This supersedes the pending hand-review statements above.
Quality final per-file technical multilabel curation remains pending.

The owner agreed to supply two additional independent capture sets with device/session
information for validation and untouched holdout. Keep the initial repeated-scene collection
in one development/calibration partition; do not manufacture independence by splitting frames.
