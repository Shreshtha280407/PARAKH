def test_queue_requires_authentication(client):
    r = client.get("/queue")
    assert r.status_code == 401


def test_queue_rejects_worker_role_token(client, worker):
    from server.app.auth import create_access_token

    token = create_access_token(worker)
    r = client.get("/queue", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_draft_assessments_are_excluded_from_the_queue(client, imported_pack, worker, assessor_headers):
    client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id})
    r = client.get("/queue", headers=assessor_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_submitted_assessment_appears_in_the_queue(db_session, client, imported_pack, worker, assessor_headers):
    from server.app import models

    assessment = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    row = db_session.get(models.Assessment, assessment["id"])
    row.status = "submitted"
    db_session.commit()

    r = client.get("/queue", headers=assessor_headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["worker_id"] == worker.id
    assert items[0]["pack_code"] == "CON/Q0602"
    assert items[0]["status"] == "submitted"


def test_admin_role_can_also_read_the_queue(client, imported_pack, worker, admin_headers):
    r = client.get("/queue", headers=admin_headers)
    assert r.status_code == 200


def test_seed_script_populates_a_non_empty_queue(db_session):
    from server.app.seed import seed

    seed(db_session)
    from server.app import models

    non_draft = db_session.query(models.Assessment).filter(models.Assessment.status != "draft").count()
    assert non_draft == 2  # submitted + in_review, per seed.py's demo workers


def test_seed_preserves_multiple_existing_assessments_for_a_demo_worker(db_session):
    from server.app import models
    from server.app.seed import seed
    from server.app.worker_tokens import generate_worker_token

    seed(db_session)
    original = db_session.query(models.Assessment).order_by(models.Assessment.id).first()
    _, token_hash = generate_worker_token()
    follow_up = models.Assessment(
        worker_id=original.worker_id, pack_id=original.pack_id,
        status="draft", worker_token_hash=token_hash, reassessment_of_id=original.id,
    )
    db_session.add(follow_up)
    db_session.commit()
    expected = {a.id: (a.worker_id, a.pack_id, a.status, a.reassessment_of_id)
                for a in db_session.query(models.Assessment).all()}

    seed(db_session)

    actual = {a.id: (a.worker_id, a.pack_id, a.status, a.reassessment_of_id)
              for a in db_session.query(models.Assessment).all()}
    assert actual == expected
