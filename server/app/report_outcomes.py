"""Signed recommendation and workflow state are separate, explicit concepts."""

def decision_for(recommendation: str) -> str:
    return "recommended" if recommendation == "RECOMMEND_CERTIFICATION" else "not_recommended"


def outcome_label(recommendation: str) -> str:
    return "Recommended" if decision_for(recommendation) == "recommended" else "Not Recommended"
