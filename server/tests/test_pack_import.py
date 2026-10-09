from server.app import models
from server.app.pack_import import import_pack, import_pack_cli


def test_import_pack_loads_all_nos_and_pcs(db_session, pack_dir):
    pack = import_pack(db_session, pack_dir)

    assert pack.qp_code == "CON/Q0602"
    assert pack.qp_version == "4.0"
    assert pack.source_pdf_sha256 == "27ef7dc3dfdcaad536bee7c1ebd73fcf7cb381e570f009cbb1b39f1060e514ad"

    nos_rows = db_session.query(models.NOS).filter_by(pack_id=pack.id).all()
    assert len(nos_rows) == 8

    pc_rows = db_session.query(models.PerformanceCriterion).join(models.NOS).filter(models.NOS.pack_id == pack.id).all()
    assert len(pc_rows) == 119

    tasks = db_session.query(models.TaskTemplate).filter_by(pack_id=pack.id).order_by(models.TaskTemplate.task_order).all()
    assert [t.task_code for t in tasks] == ["T1", "T2", "T3", "T4", "T5"]
    assert sum(t.budget_bytes for t in tasks) == 120 * 1024 * 1024


def test_import_pack_is_idempotent(db_session, pack_dir):
    first = import_pack(db_session, pack_dir)
    second = import_pack(db_session, pack_dir)
    assert first.id == second.id
    assert db_session.query(models.QualificationPack).count() == 1


def test_rubric_items_only_exist_for_task_evidence_pathway_pcs(db_session, pack_dir):
    pack = import_pack(db_session, pack_dir)
    pathway_count = (
        db_session.query(models.PerformanceCriterion)
        .join(models.NOS)
        .filter(models.NOS.pack_id == pack.id, models.PerformanceCriterion.evidence_pathway == "TASK_EVIDENCE_PATHWAY")
        .count()
    )
    rubric_count = (
        db_session.query(models.RubricItem)
        .join(models.PerformanceCriterion)
        .join(models.NOS)
        .filter(models.NOS.pack_id == pack.id)
        .count()
    )
    assert pathway_count == 71
    assert rubric_count == 71


def test_not_applicable_pc_flag_survives_import(db_session, pack_dir):
    pack = import_pack(db_session, pack_dir)
    pc = (
        db_session.query(models.PerformanceCriterion)
        .join(models.NOS)
        .filter(models.NOS.pack_id == pack.id, models.PerformanceCriterion.full_id == "CON/N0603.PC16")
        .one()
    )
    assert pc.mvp_applicability == "NOT_APPLICABLE_IN_MVP"

    other_pc = (
        db_session.query(models.PerformanceCriterion)
        .join(models.NOS)
        .filter(models.NOS.pack_id == pack.id, models.PerformanceCriterion.full_id == "CON/N0602.PC1")
        .one()
    )
    assert other_pc.mvp_applicability == "ASSESSABLE"


def test_import_pack_cli_rejects_a_pack_that_fails_p1_validators(db_session, tmp_path, pack_dir):
    import shutil
    import json

    broken = tmp_path / "broken_pack"
    shutil.copytree(pack_dir, broken)
    qp = json.loads((broken / "qp.json").read_text())
    qp["version"] = "3.0"  # drifts from source.json -- same defect as tests/fixtures/pack_wrong_qp_version
    (broken / "qp.json").write_text(json.dumps(qp))

    import pytest
    with pytest.raises(RuntimeError, match="audit_qp_traceability"):
        import_pack_cli(broken, db_session)
