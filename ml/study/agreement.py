#!/usr/bin/env python3
"""Agreement statistics with paired assessment-package cluster bootstrap.

All PC agreement metrics use the SAME complete scored item set in BOTH
conditions. MAE further requires a demonstrated synthetic reference. Explicit
exclusion accounting makes status decisions and missingness visible.
"""
import argparse
import itertools
import math
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.study.common import (CONDITIONS, HERE, LIMITATION, MARKER, digest, load_pack,
                             fixed_status, read_csv, validate_score_record, write_json)
from ml.study.outcome_adapter import OUTCOMES, derive_outcome

METRICS = {
    "mean_pairwise_qwk": ("Mean pairwise QWK", "higher"),
    "fleiss_kappa": ("Fleiss' kappa", "higher"),
    "exact_agreement_pct": ("Exact agreement (%)", "higher"),
    "mean_rating_sd": ("Mean rating SD", "lower"),
    "mae": ("MAE vs synthetic reference", "lower"),
    "outcome_fleiss_kappa": ("Outcome Fleiss' kappa", "higher"),
    "outcome_exact_agreement_pct": ("Outcome exact agreement (%)", "higher"),
}


def qwk_from_confusion(confusion):
    """Quadratic disagreement weights (i-j)^2, fixed categories 0,1,2,3."""
    n = sum(confusion)
    if n == 0:
        return None
    row = [sum(confusion[i * 4:i * 4 + 4]) for i in range(4)]
    col = [sum(confusion[j::4]) for j in range(4)]
    observed = sum(confusion[i * 4 + j] * (i - j) ** 2 for i in range(4) for j in range(4))
    expected = sum(row[i] * col[j] * (i - j) ** 2 for i in range(4) for j in range(4)) / n
    return 1 - observed / expected if expected > 0 else None


def quadratic_weighted_kappa(a, b):
    if len(a) != len(b):
        raise ValueError("kappa requires paired equal-length inputs")
    confusion = [0] * 16
    for x, y in zip(a, b):
        if type(x) is not int or type(y) is not int or x not in range(4) or y not in range(4):
            raise ValueError("kappa levels must be integers 0–3")
        confusion[4 * x + y] += 1
    return qwk_from_confusion(confusion)


def fleiss_from_totals(n, r, counts, pi_sum):
    if n == 0 or r < 2:
        return None
    expected = sum((count / (n * r)) ** 2 for count in counts)
    if math.isclose(expected, 1, rel_tol=0, abs_tol=1e-15):
        return None
    return (pi_sum / n - expected) / (1 - expected)


def fleiss_kappa(table):
    """Rows are category counts, each with the same number of ratings."""
    if not table:
        return None
    k, r = len(table[0]), sum(table[0])
    if k == 0 or any(len(row) != k or sum(row) != r for row in table):
        raise ValueError("Fleiss requires a common category set and constant rater count")
    if any(type(x) is not int or x < 0 for row in table for x in row):
        raise ValueError("Fleiss counts must be nonnegative integers")
    if r < 2:
        return None
    counts = [sum(row[c] for row in table) for c in range(k)]
    pi = sum(sum(x * (x - 1) for x in row) / (r * (r - 1)) for row in table)
    return fleiss_from_totals(len(table), r, counts, pi)


def population_sd(levels):
    if len(levels) < 2:
        return None
    mean = sum(levels) / len(levels)
    return math.sqrt(sum((x - mean) ** 2 for x in levels) / len(levels))


@dataclass
class Summary:
    """Additive sufficient statistics: each sampled cluster contributes once per draw."""
    n: int = 0
    counts: list = field(default_factory=lambda: [0] * 4)
    pi_sum: float = 0.0
    exact: int = 0
    sd_sum: float = 0.0
    mae_sum: float = 0.0
    mae_n: int = 0
    confusion: list = field(default_factory=list)
    outcome_n: int = 0
    outcome_counts: list = field(default_factory=lambda: [0] * 4)
    outcome_pi: float = 0.0
    outcome_exact: int = 0

    @classmethod
    def empty(cls, r):
        return cls(confusion=[[0] * 16 for _ in itertools.combinations(range(r), 2)])

    def add(self, other):
        for name in ("n", "pi_sum", "exact", "sd_sum", "mae_sum", "mae_n",
                     "outcome_n", "outcome_pi", "outcome_exact"):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        for name in ("counts", "outcome_counts"):
            setattr(self, name, [a + b for a, b in zip(getattr(self, name), getattr(other, name))])
        self.confusion = [[a + b for a, b in zip(x, y)] for x, y in zip(self.confusion, other.confusion)]
        return self

    def add_item(self, levels, reference):
        r = len(levels)
        self.n += 1
        counts = [levels.count(i) for i in range(4)]
        self.counts = [a + b for a, b in zip(self.counts, counts)]
        if r >= 2:
            self.pi_sum += sum(x * (x - 1) for x in counts) / (r * (r - 1))
            self.exact += len(set(levels)) == 1
            self.sd_sum += population_sd(levels)
        for confusion, (a, b) in zip(self.confusion, itertools.combinations(levels, 2)):
            confusion[4 * a + b] += 1
        if reference is not None:
            self.mae_sum += sum(abs(x - reference) for x in levels)
            self.mae_n += r

    def add_outcome(self, levels):
        r = len(levels)
        self.outcome_n += 1
        counts = [levels.count(i) for i in range(4)]
        self.outcome_counts = [a + b for a, b in zip(self.outcome_counts, counts)]
        if r >= 2:
            self.outcome_pi += sum(x * (x - 1) for x in counts) / (r * (r - 1))
            self.outcome_exact += len(set(levels)) == 1


def metrics(summary, r):
    pairwise = [qwk_from_confusion(c) for c in summary.confusion]
    return {
        # Do not silently average only defined pairs when another pair is undefined.
        "mean_pairwise_qwk": sum(pairwise) / len(pairwise) if pairwise and all(x is not None for x in pairwise) else None,
        "fleiss_kappa": fleiss_from_totals(summary.n, r, summary.counts, summary.pi_sum),
        "exact_agreement_pct": 100 * summary.exact / summary.n if summary.n and r >= 2 else None,
        "mean_rating_sd": summary.sd_sum / summary.n if summary.n and r >= 2 else None,
        "mae": summary.mae_sum / summary.mae_n if summary.mae_n else None,
        "outcome_fleiss_kappa": fleiss_from_totals(summary.outcome_n, r, summary.outcome_counts, summary.outcome_pi),
        "outcome_exact_agreement_pct": 100 * summary.outcome_exact / summary.outcome_n if summary.outcome_n and r >= 2 else None,
    }


def cluster_draw(packages, rng):
    """Explicit internal draw identities keep repeated packages distinct.

    Summing sufficient statistics is exactly equivalent to expanding rows with
    (draw_id, package, pc) identities, without re-grouping repeated package IDs.
    """
    return [(f"draw-{i:05d}", packages[rng.randrange(len(packages))]) for i in range(len(packages))]


def sum_draw(contributions, draws, condition, r):
    total = Summary.empty(r)
    for _draw_id, package in draws:
        total.add(contributions[condition][package])
    return total


def percentile(values, q):
    values = sorted(values)
    location = (len(values) - 1) * q
    low = math.floor(location)
    high = math.ceil(location)
    return values[low] + (values[high] - values[low]) * (location - low)


def prepare(ratings, references, expected_raters=None):
    """Build the paired cohort and an exhaustive, disjoint item exclusion ledger."""
    roster = sorted(expected_raters if expected_raters is not None else {r["rater"] for r in ratings})
    if not roster or len(roster) != len(set(roster)):
        raise ValueError("expected raters must be nonempty and unique")
    if {r["rater"] for r in ratings} - set(roster):
        raise ValueError("ratings contain a rater outside the expected roster")
    pack = load_pack()
    identities, grouped, seen = {}, {c: defaultdict(dict) for c in CONDITIONS}, set()
    reference = {}
    for row in references:
        key = (row["package"], row["pc"])
        if key in reference:
            raise ValueError(f"duplicate reference {key}")
        reference[key] = row
    for row in [*references, *ratings]:
        validate_score_record(row)
        if "synthetic" in row and row["synthetic"] != "true":
            raise ValueError("this study interface accepts explicitly synthetic records only")
        if row["pc"] in pack["catalog"]:
            item = pack["catalog"][row["pc"]]
            if row["nos"] != item["nos"] or row["task"] != item["task"]:
                raise ValueError("known PC has incorrect pinned NOS/task metadata")
            status = fixed_status(item)
            if (status and row["evidence_status"] != status) or (not status and row["evidence_status"] not in ("DEMONSTRATED", "NOT_OBSERVABLE")):
                raise ValueError("known PC has incorrect pinned applicability/status")
        key = (row["package"], row["pc"])
        identity = (row["nos"], row["task"], row["scenario"])
        if identities.setdefault(key, identity) != identity:
            raise ValueError(f"inconsistent NOS/task/scenario for {key}")
    for row in ratings:
        condition = row["condition"]
        if condition not in CONDITIONS:
            raise ValueError("unknown condition")
        key = (row["package"], row["pc"])
        identity = (condition, *key, row["rater"])
        if identity in seen:
            raise ValueError(f"duplicate rating {identity}")
        seen.add(identity)
        grouped[condition][key][row["rater"]] = row
    package_sets = [{key[0] for key in grouped[c]} for c in CONDITIONS]
    packages = sorted(set.intersection(*package_sets))
    keys = sorted(set(identities))
    contributions = {c: {p: Summary.empty(len(roster)) for p in packages} for c in CONDITIONS}
    excluded, excluded_records = Counter(), Counter()
    retained = 0
    missing_slots = {c: 0 for c in CONDITIONS}
    absent_reference, unscored_reference = 0, 0
    for key in keys:
        groups = [grouped[c].get(key, {}) for c in CONDITIONS]
        rows = [v for group in groups for v in group.values()]
        for c, group in zip(CONDITIONS, groups):
            missing_slots[c] += len(set(roster) - set(group))
        if key[0] not in contributions[CONDITIONS[0]]:
            reason = "package_not_present_in_both_conditions"
        elif any(set(group) != set(roster) for group in groups):
            reason = "incomplete_rater_group_in_either_condition"
        elif any(row["evidence_status"] in ("NOT_APPLICABLE_IN_MVP", "DECLARATION_OR_ASSESSOR_NOTE") for row in rows):
            reason = "fixed_unscored_status_in_either_condition"
        elif any(row["evidence_status"] != "DEMONSTRATED" for row in rows):
            reason = "not_observable_in_either_condition"
        else:
            reason = None
        if reason:
            excluded[reason] += 1
            excluded_records[reason] += len(rows)
            continue
        retained += 1
        ref = reference.get(key)
        if ref is None:
            absent_reference += 1
        elif ref["evidence_status"] != "DEMONSTRATED":
            unscored_reference += 1
        ref_level = ref["level"] if ref is not None and ref["evidence_status"] == "DEMONSTRATED" else None
        for c, group in zip(CONDITIONS, groups):
            levels = [group[r]["level"] for r in roster]
            contributions[c][key[0]].add_item(levels, ref_level)
    # Outcome categories are nominal, derived only for complete pinned-pack packages.
    required = {i["pc_id"] for i in pack["rubric"]["items"]}
    outcome_distribution = {c: Counter() for c in CONDITIONS}
    outcome_excluded = 0
    for package in packages:
        complete = all(all(rater in grouped[c].get((package, pc), {}) for pc in required)
                       for c in CONDITIONS for rater in roster)
        if not complete:
            outcome_excluded += 1
            continue
        for c in CONDITIONS:
            values = []
            for rater in roster:
                records = [grouped[c][(package, pc)][rater] for pc in sorted(required)]
                value = derive_outcome(records, pack).outcome
                outcome_distribution[c][value] += 1
                values.append(OUTCOMES.index(value))
            contributions[c][package].add_outcome(values)
    audit = {
        "input_rating_records": len(ratings), "reference_records": len(references),
        "raters": roster, "packages_by_condition": {c: sorted(s) for c, s in zip(CONDITIONS, package_sets)},
        "common_packages": packages, "candidate_package_pc_items": len(keys),
        "retained_complete_scored_items": retained, "excluded_items_by_reason": dict(sorted(excluded.items())),
        "excluded_existing_rating_records_by_reason": dict(sorted(excluded_records.items())),
        "missing_rater_slots_by_condition": missing_slots,
        "reference_rows_without_any_ratings": sum(key not in grouped["manual"] and key not in grouped["rubric_assisted"] for key in reference),
        "mae_excluded_items_missing_reference": absent_reference,
        "mae_excluded_items_unscored_reference": unscored_reference,
        "input_status_counts": {c: dict(sorted(Counter(r["evidence_status"] for r in ratings if r["condition"] == c).items())) for c in CONDITIONS},
        "outcome_excluded_common_packages_incomplete_pack": outcome_excluded,
        "outcome_distributions": outcome_distribution,
    }
    return packages, roster, contributions, audit


def analyze(ratings, references=(), *, bootstrap=2000, seed=42, expected_raters=None):
    if bootstrap < 0:
        raise ValueError("bootstrap must be nonnegative")
    packages, roster, contributions, audit = prepare(ratings, references, expected_raters)
    r = len(roster)
    full_draw = [(f"point-{i}", p) for i, p in enumerate(packages)]
    totals = {c: sum_draw(contributions, full_draw, c, r) for c in CONDITIONS}
    points = {c: metrics(totals[c], r) for c in CONDITIONS}
    differences = {m: (points["rubric_assisted"][m] - points["manual"][m]
                       if all(points[c][m] is not None for c in CONDITIONS) else None) for m in METRICS}
    samples = {m: [] for m in METRICS}
    rng = random.Random(seed)
    if packages:
        for _ in range(bootstrap):
            draws = cluster_draw(packages, rng)
            sample = {c: metrics(sum_draw(contributions, draws, c, r), r) for c in CONDITIONS}
            for m in METRICS:
                if all(sample[c][m] is not None for c in CONDITIONS):
                    samples[m].append(sample["rubric_assisted"][m] - sample["manual"][m])
    ci = {}
    for m in METRICS:
        values = samples[m]
        reason = None
        if len(packages) < 2:
            reason = "at least two common assessment packages are required for cluster uncertainty"
        elif bootstrap < 2:
            reason = "bootstrap disabled or fewer than two iterations"
        elif differences[m] is None:
            reason = "point statistic is undefined"
        elif len(values) < max(2, math.ceil(0.95 * bootstrap)):
            reason = "more than 5% of bootstrap differences are undefined"
        ci[m] = {"low": percentile(values, 0.025) if reason is None else None,
                 "high": percentile(values, 0.975) if reason is None else None,
                 "defined_replicates": len(values), "undefined_replicates": bootstrap - len(values),
                 "unavailable_reason": reason}
    pairs = {c: {f"{a} / {b}": qwk_from_confusion(confusion)
                 for (a, b), confusion in zip(itertools.combinations(roster, 2), totals[c].confusion)} for c in CONDITIONS}
    reasons = {}
    for c in CONDITIONS:
        reasons[c] = {}
        for m in METRICS:
            if points[c][m] is not None:
                continue
            if m == "mae":
                reason = "no paired scored ratings with a demonstrated reference"
            elif r < 2:
                reason = "at least two raters are required"
            elif (totals[c].outcome_n if m.startswith("outcome_") else totals[c].n) == 0:
                reason = "no complete pinned-pack outcomes" if m.startswith("outcome_") else "no common complete scored items"
            else:
                reason = "zero expected disagreement / degenerate category marginals (at least one pair for mean QWK)"
            reasons[c][m] = reason
    return {"synthetic": True, "provenance": MARKER, "limitation": LIMITATION,
            "simulation_metadata": {"policies": sorted({str(row.get('policy', 'unspecified')) for row in ratings}),
                                    "seeds": sorted({str(row.get('simulation_seed', 'unspecified')) for row in ratings})},
            "bootstrap": {"iterations": bootstrap, "seed": seed, "unit": "assessment package",
                          "method": "paired cluster percentile, 2.5/97.5%, linear interpolation"},
            "metrics": points, "differences": differences, "ci95": ci, "pairwise_qwk": pairs,
            "unavailable_reasons": reasons, "audit": audit}


def fmt(value):
    return "unavailable" if value is None else f"{value:.6f}"


def render_report(result):
    pack = load_pack()
    audit = result["audit"]
    policies = result["simulation_metadata"]["policies"]
    if policies == ["baseline"]:
        simulation_text = "Baseline simulation assigns the same parameters to both conditions and draws independent errors. Differences reflect controlled simulation noise; they are not a measured product effect."
    elif policies == ["identical"]:
        simulation_text = "Identical-conditions control uses the same parameters and random draws in both conditions. Its zero differences are an engineering control, not a measured product effect."
    else:
        simulation_text = "Simulation policy is unspecified or mixed; no condition-effect assumption can be inferred from these inputs. These synthetic differences are not a measured product effect."
    lines = ["# D3 synthetic engineering validation", "", f"**{LIMITATION}**", "",
             pack["rubric"]["rules"]["disclaimer"], f"Rubric status: {pack['rubric']['status']}.", "",
             f"QP {pack['qp']['qp_code']} v{pack['qp']['version']}; rubric `{pack['rubric']['rubric_id']}`.", "",
             "No real assessors participated; no expert labels were collected. Original physical D3/D5 requirements remain unfulfilled.", "",
             "| Metric | Manual | Rubric assisted | Difference (assisted − manual) | 95% package bootstrap CI | Improvement direction |",
             "|---|---:|---:|---:|---|---|"]
    for key, (label, direction) in METRICS.items():
        ci = result["ci95"][key]
        interval = f"[{fmt(ci['low'])}, {fmt(ci['high'])}]" if ci["low"] is not None else "unavailable"
        lines.append(f"| {label} | {fmt(result['metrics']['manual'][key])} | {fmt(result['metrics']['rubric_assisted'][key])} | {fmt(result['differences'][key])} | {interval} | {direction} |")
    lines += ["", "## Interpretation and method", "",
              simulation_text + " Labels are not inferred or corrected by the analysis.",
              f"Simulation metadata: policies {policies}; seeds {result['simulation_metadata']['seeds']}.", "",
              "Quadratic-weighted Cohen kappa uses fixed ordered categories 0–3 and weights (i−j)². The mean requires every rater pair to be defined. Fleiss kappa uses pooled category marginals and a constant full roster. Exact agreement is the percentage of item groups where every rater gives the same level. Mean SD averages population SD (ddof=0) per item. MAE is an unweighted mean over rater/item observations with a demonstrated reference; PC marks do not weight these statistics.", "",
              "All PC statistics use the joint complete, demonstrated item set across both conditions. MAE additionally excludes missing/unscored reference labels. This complete-case comparison can select easier evidence; status counts and excluded items below expose that limitation. Unobservable, not-applicable and declaration-only values never become scored zeroes. With one rater only MAE is meaningful.", "",
              "Outcome agreement is nominal Fleiss kappa and exact agreement over complete 71-PC packages, including explicit unobservable/not-applicable statuses. It calls `server/app/outcome.py` with the existing scoring Decimal rounding. The existing engine keeps not-applicable marks in the denominator; this adapter preserves that behavior. These are computed recommendations, not official certification decisions.", "",
              f"Bootstrap: {result['bootstrap']['iterations']} draws, seed {result['bootstrap']['seed']}. Resample entire common packages with replacement, using the same draw in both conditions and a distinct internal identity for every repeated draw. Additive per-package sufficient statistics preserve all PCs and raters without collapsing repeated packages. Percentile endpoints use linear interpolation. No row bootstrap or normal approximation is used.", "",
              "CIs require at least two clusters, a defined point difference and ≥95% defined replicates (at least two). Undefined replicates are counted below; intervals then describe the defined replicates. These intervals describe the synthetic package population, not people, independent field evidence or causal effects.", "",
              "## Pairwise quadratic-weighted Cohen kappa", "",
              "| Rater pair | Manual | Rubric assisted |", "|---|---:|---:|"]
    for pair in result["pairwise_qwk"]["manual"]:
        lines.append(f"| {pair} | {fmt(result['pairwise_qwk']['manual'][pair])} | {fmt(result['pairwise_qwk']['rubric_assisted'][pair])} |")
    lines += ["", "## Cohort and exclusions", "",
              f"Input: {audit['input_rating_records']} rating records; {audit['reference_records']} reference records; {len(audit['raters'])} raters; {len(audit['common_packages'])} common packages.",
              f"Candidate package/PC identities: {audit['candidate_package_pc_items']}; retained complete scored items: {audit['retained_complete_scored_items']}.", "",
              "Item exclusions are mutually exclusive, in priority order: noncommon package, incomplete roster, fixed unscored status, not observable. MAE exclusions are additional and apply only to retained items.", "", "```json"]
    import json
    lines += [json.dumps(audit, indent=2, sort_keys=True), "```", "", "## Undefined values and bootstrap availability", ""]
    for c, reasons in result["unavailable_reasons"].items():
        for m, reason in reasons.items():
            lines.append(f"- {c}, {METRICS[m][0]}: unavailable — {reason}.")
    for m, ci in result["ci95"].items():
        lines.append(f"- {METRICS[m][0]}: {ci['defined_replicates']} defined / {ci['undefined_replicates']} undefined bootstrap differences" + (f"; CI unavailable: {ci['unavailable_reason']}" if ci["unavailable_reason"] else "") + ".")
    lines += ["", "## Provenance", "", "```json", json.dumps(result.get("input_sha256", {}), indent=2, sort_keys=True), "```", "",
              "Statistical cross-check sources: [scikit-learn QWK](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.cohen_kappa_score.html), [statsmodels Fleiss kappa](https://www.statsmodels.org/stable/generated/statsmodels.stats.inter_rater.fleiss_kappa.html). Unit tests compare these independent implementations and hand-calculated fixtures.", ""]
    return "\n".join(lines)


def run(ratings_path, reference_path=None, *, bootstrap=2000, seed=42, out=HERE / "reports/synthetic_validation.md", expected_raters=None):
    ratings = read_csv(ratings_path)
    reference = read_csv(reference_path, reference=True) if reference_path else []
    result = analyze(ratings, reference, bootstrap=bootstrap, seed=seed, expected_raters=expected_raters)
    result["input_sha256"] = {"ratings": digest(ratings_path), "reference": digest(reference_path) if reference_path else None,
                              "outcome_engine": digest(HERE.parents[1] / "server/app/outcome.py"),
                              "analysis_source": digest(Path(__file__))}
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(result), encoding="utf-8")
    write_json(out.with_suffix(".json"), result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ratings", type=Path)
    parser.add_argument("--reference", "--gold", dest="reference", type=Path,
                        help="synthetic reference CSV (--gold is a legacy alias, not expert gold)")
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--raters", nargs="+", help="explicit expected roster (otherwise union of observed raters)")
    parser.add_argument("--out", type=Path, default=HERE / "reports/synthetic_validation.md")
    args = parser.parse_args()
    try:
        result = run(args.ratings, args.reference, bootstrap=args.bootstrap, seed=args.seed,
                     out=args.out, expected_raters=args.raters)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"validation failed: {exc}\n")
    print(f"{MARKER}: {result['audit']['retained_complete_scored_items']} paired scored items; report {args.out}")


if __name__ == "__main__":
    main()
