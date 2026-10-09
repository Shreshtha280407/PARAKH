def test_create_assessment_seeds_fixed_five_tasks_in_order(client, imported_pack, worker):
    r = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id})
    assert r.status_code == 201
    body = r.json()
    assert [t["task_code"] for t in body["tasks"]] == ["T1", "T2", "T3", "T4", "T5"]
    assert [t["budget_bytes"] for t in body["tasks"]] == [
        15 * 1024 * 1024, 20 * 1024 * 1024, 30 * 1024 * 1024, 25 * 1024 * 1024, 30 * 1024 * 1024,
    ]


def test_create_assessment_rejects_unknown_worker(client, imported_pack):
    r = client.post("/assessments", json={"worker_id": 999999, "pack_id": imported_pack.id})
    assert r.status_code == 404


def test_get_assessment_round_trips(client, imported_pack, worker):
    created = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.get(f"/assessments/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_add_evidence_metadata_within_budget_succeeds(client, imported_pack, worker):
    assessment = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    r = client.post(
        f"/assessments/{assessment['id']}/evidence",
        json={"task_code": "T1", "kind": "photo", "mime": "image/jpeg", "declared_size_bytes": 1024 * 1024},
    )
    assert r.status_code == 201
    assert r.json()["declared_size_bytes"] == 1024 * 1024


def test_add_evidence_metadata_over_task_budget_is_rejected(client, imported_pack, worker):
    assessment = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    # T1's budget is 15 MB
    r = client.post(
        f"/assessments/{assessment['id']}/evidence",
        json={"task_code": "T1", "kind": "video", "mime": "video/mp4", "declared_size_bytes": 16 * 1024 * 1024},
    )
    assert r.status_code == 409
    assert "T1" in r.json()["detail"]


def test_filling_all_five_tasks_to_exactly_120mb_succeeds(client, imported_pack, worker):
    assessment = client.post("/assessments", json={"worker_id": worker.id, "pack_id": imported_pack.id}).json()
    for task_code, mb in [("T1", 15), ("T2", 20), ("T3", 30), ("T4", 25), ("T5", 30)]:
        r = client.post(
            f"/assessments/{assessment['id']}/evidence",
            json={"task_code": task_code, "kind": "video", "mime": "video/mp4", "declared_size_bytes": mb * 1024 * 1024},
        )
        assert r.status_code == 201, r.json()
    done = client.get(f"/assessments/{assessment['id']}").json()
    assert done["total_bytes_used"] == 120 * 1024 * 1024


def test_quota_total_check_fires_when_a_tasks_own_budget_has_room(db_session, imported_pack, worker):
    """T1-T5's budgets sum to exactly the 120 MB total (15+20+30+25+30), so a
    request that respects its own task's budget can never exceed the total
    either -- the per-task checks alone are collectively sufficient for this
    pack. The total check is still real defensive code (e.g. a future pack
    whose task budgets don't sum to the total exactly), so it's exercised
    directly here against a synthetic over-provisioned task rather than
    through the unreachable-by-construction HTTP path."""
    from server.app import models, quota

    assessment = models.Assessment(worker_id=worker.id, pack_id=imported_pack.id)
    db_session.add(assessment)
    db_session.flush()
    # Another task on the SAME assessment has already eaten 119 of the 120 MB total.
    hungry_task = models.AssessmentTask(assessment_id=assessment.id, task_code="T2", budget_bytes=120 * 1024 * 1024)
    db_session.add(hungry_task)
    db_session.flush()
    db_session.add(models.EvidenceItem(
        assessment_task_id=hungry_task.id, kind="video", mime="video/mp4", declared_size_bytes=119 * 1024 * 1024,
    ))
    # This task itself still has plenty of its own budget untouched.
    task = models.AssessmentTask(assessment_id=assessment.id, task_code="T1", budget_bytes=50 * 1024 * 1024)
    db_session.add(task)
    db_session.commit()

    # Task check alone would pass (5 MB <= its 50 MB budget), but only 1 MB remains of the 120 MB total.
    import pytest
    with pytest.raises(quota.QuotaExceeded, match="120 MB"):
        quota.check_quota(db_session, task, 5 * 1024 * 1024, imported_pack.final_evidence_budget_bytes)
