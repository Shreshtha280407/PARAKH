import pytest

from server.app import models
from server.app.auth import verify_password
from server.app.provision_assessor import provision_assessor


def test_provision_creates_a_new_assessor_with_no_other_rows(db_session):
    user = provision_assessor(db_session, "new.assessor@real.example", "a-real-password", "Real Assessor")
    assert user.role == "assessor"
    assert user.email == "new.assessor@real.example"
    assert verify_password("a-real-password", user.password_hash)
    # No demo workers/assessments were created as a side effect.
    assert db_session.query(models.User).count() == 1
    assert db_session.query(models.Assessment).count() == 0


def test_provision_is_idempotent_and_resets_the_password(db_session):
    first = provision_assessor(db_session, "reset@real.example", "first-password", "First Name")
    second = provision_assessor(db_session, "reset@real.example", "second-password", "Updated Name")
    assert first.id == second.id
    assert db_session.query(models.User).count() == 1
    assert second.display_name == "Updated Name"
    assert verify_password("second-password", second.password_hash)
    assert not verify_password("first-password", second.password_hash)


def test_provision_can_create_an_admin(db_session):
    user = provision_assessor(db_session, "admin@real.example", "a-real-password", "Admin User", role="admin")
    assert user.role == "admin"


def test_provision_rejects_a_short_password(db_session):
    with pytest.raises(ValueError, match="at least 8 characters"):
        provision_assessor(db_session, "x@real.example", "short", "X")


def test_provision_refuses_to_hijack_a_worker_email(db_session):
    worker = models.User(role="worker", display_name="A Worker", phone="9000000055", email="shared@real.example")
    db_session.add(worker)
    db_session.commit()

    with pytest.raises(ValueError, match="non-assessor account"):
        provision_assessor(db_session, "shared@real.example", "a-real-password", "Not Actually A Worker")
