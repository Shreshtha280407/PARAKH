"""Create (or reset the password of) exactly one real assessor/admin
account, with no other side effect.

This is deliberately separate from `server/app/seed.py`: seed.py also
creates demo workers and demo assessments, which is correct for a local
dev/demo stack but is exactly the kind of fake record the owner does not
want appearing in a real hosted deployment's database (see "No fake data
in the user-facing product" in the P10 brief). A real operator standing up
a hosted PARAKH instance for the first time needs a way to create their own
login without also getting three synthetic workers and assessments mixed
into production data.

Usage (local):
    server/.venv/bin/python -m app.provision_assessor \
        --email assessor@realorg.example --display-name "Jane Doe" --role assessor

Usage (Docker):
    docker compose exec api python -m app.provision_assessor \
        --email assessor@realorg.example --display-name "Jane Doe"

The password is never accepted as a CLI argument (that would leak into
shell history and `ps`/process-list output) and is never logged. It is
read from the controlling terminal via getpass; for non-interactive
scripted provisioning (CI, a one-shot container init script with no TTY),
set PROVISION_ASSESSOR_PASSWORD in the environment instead and it will be
used without a prompt -- unset it again immediately afterwards.

Idempotent: running this again for the same email updates the display name
and resets the password, rather than failing or creating a duplicate.
"""
import argparse
import getpass
import os
import sys

from . import models
from .auth import hash_password
from .db import SessionLocal


def provision_assessor(
    db,
    email: str,
    password: str,
    display_name: str,
    role: str = "assessor",
) -> models.User:
    if role not in ("assessor", "admin"):
        raise ValueError(f"role must be 'assessor' or 'admin', got {role!r}")
    if not password or len(password) < 8:
        raise ValueError("password must be at least 8 characters")

    user = db.query(models.User).filter_by(email=email).one_or_none()
    if user is None:
        user = models.User(role=role, display_name=display_name, email=email)
        db.add(user)
    else:
        if user.role not in ("assessor", "admin"):
            raise ValueError(f"email {email!r} already belongs to a non-assessor account (role={user.role!r})")
        user.role = role
        user.display_name = display_name
    user.password_hash = hash_password(password)
    db.commit()
    db.refresh(user)
    return user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--role", choices=["assessor", "admin"], default="assessor")
    args = parser.parse_args(argv)

    password = os.environ.get("PROVISION_ASSESSOR_PASSWORD")
    if password:
        print("Using password from PROVISION_ASSESSOR_PASSWORD (unset that variable after this runs).")
    else:
        if not sys.stdin.isatty():
            print(
                "No TTY available and PROVISION_ASSESSOR_PASSWORD is unset -- cannot prompt "
                "for a password. Set PROVISION_ASSESSOR_PASSWORD for non-interactive use.",
                file=sys.stderr,
            )
            return 1
        password = getpass.getpass("New password for this account: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords did not match.", file=sys.stderr)
            return 1

    db = SessionLocal()
    try:
        user = provision_assessor(db, args.email, password, args.display_name, args.role)
    except ValueError as e:
        print(f"Could not provision account: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"Provisioned {user.role} account id={user.id} email={user.email!r}. No demo data was created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
