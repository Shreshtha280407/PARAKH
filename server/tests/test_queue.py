def test_draft_assessments_are_excluded_from_the_queue(client, imported_pack, worker):
    client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id})
    r = client.get("/queue")
    assert r.status_code == 200
    assert r.json() == []


def test_submitted_assessment_appears_in_the_queue(db_session, client, imported_pack, worker):
    from server.app import models

    assessment = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    row = db_session.get(models.Assessment, assessment["id"])
    row.status = "submitted"
    db_session.commit()

    r = client.get("/queue")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["worker_id"] == worker.id
    assert items[0]["pack_code"] == "CON/Q0602"
    assert items[0]["status"] == "submitted"


def test_seed_script_populates_a_non_empty_queue(db_session):
    from server.app.seed import seed

    seed(db_session)
    from server.app import models

    non_draft = db_session.query(models.Assessment).filter(models.Assessment.status != "draft").count()
    assert non_draft == 2  # submitted + in_review, per seed.py's demo workers
