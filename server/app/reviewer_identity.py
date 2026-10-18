"""Identity declarations are distinct from email verification and reviewer permission."""
from dataclasses import dataclass


@dataclass
class ReviewerActor:
    display_name: str
    email: str
    session_id: str
    id: None = None
    role: str = "reviewer"
    account_id: str | None = None


def identity(actor) -> dict:
    if isinstance(actor, ReviewerActor):
        return {"name": actor.display_name, "email": actor.email,
                "email_verified": actor.account_id is None, "name_verified": False,
                "authorization": "password_account" if actor.account_id else "operator_allowlist",
                "account_id": actor.account_id, "session_id": actor.session_id}
    return {"name": actor.display_name, "email": actor.email,
            "email_verified": False, "name_verified": False,
            "authorization": "organizational_account", "user_id": actor.id}
