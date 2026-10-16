"""Read-only adapter to the production outcome function; no database or API imports."""
from decimal import Decimal
from types import SimpleNamespace as NS

from .common import fixed_status, load_pack, validate_score_record

# Direct CLI callers arrange the repository path before importing this module.
from server.app.outcome import compute_outcome

OUTCOMES = ("RECOMMEND_CERTIFICATION", "PARTIALLY_COMPETENT",
            "NOT_YET_COMPETENT", "INSUFFICIENT_EVIDENCE")


def derive_outcome(records, pack=None):
    pack = pack or load_pack()
    expected = {i["pc_id"] for i in pack["rubric"]["items"]}
    scores_by_pc = {}
    for record in records:
        validate_score_record(record)
        if record["pc"] not in pack["catalog"]:
            raise ValueError("unknown PC in outcome input")
        if record["pc"] not in expected:
            continue
        if record["pc"] in scores_by_pc:
            raise ValueError("duplicate PC in outcome input")
        fixed = fixed_status(pack["catalog"][record["pc"]])
        if fixed and record["evidence_status"] != fixed:
            raise ValueError("fixed not-applicable PC cannot be scored")
        if not fixed and record["evidence_status"] not in ("DEMONSTRATED", "NOT_OBSERVABLE"):
            raise ValueError("invalid outcome status for assessable PC")
        scores_by_pc[record["pc"]] = record
    if set(scores_by_pc) != expected:
        raise ValueError("outcome requires all pinned task-linked PCs, including explicit missing statuses")
    rows, scores = [], {}
    nos_titles = {n["code"]: n["title"] for n in pack["qp"]["nos"]}
    for item in pack["rubric"]["items"]:
        pc, nos, marks = item["pc_id"], item["nos"], Decimal(str(item["marks"]))
        rows.append((NS(marks=marks, critical=item["critical"]), NS(id=pc, full_id=pc),
                     NS(id=nos, code=nos, title=nos_titles[nos])))
        record = scores_by_pc[pc]
        level, status = record["level"], record["evidence_status"]
        # Match routers/scoring.py's Decimal arithmetic and per-PC rounding.
        # Non-scored levels stay None; zero marks here are the engine's
        # bookkeeping convention, not an invented observed score of zero.
        awarded = ((marks * Decimal(level) / Decimal(3)).quantize(Decimal("0.01"))
                   if status == "DEMONSTRATED" else Decimal("0.00"))
        scores[pc] = NS(score_level=level, evidence_status=status, marks_awarded=awarded,
                        scored_at="SYNTHETIC_REVIEW_MARKER")
    return compute_outcome(rows, scores, pack["qp"]["minimum_aggregate_passing_percent"])
