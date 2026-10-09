def test_pack_import_requires_authentication(client):
    r = client.post("/admin/packs/import", json={"pack_dir": "packs/ae-con-q0602"})
    assert r.status_code == 401


def test_pack_import_rejects_assessor_role(client, assessor_headers):
    """Assessor is not admin -- pack management is admin-only."""
    r = client.post("/admin/packs/import", json={"pack_dir": "packs/ae-con-q0602"}, headers=assessor_headers)
    assert r.status_code == 403


def test_pack_import_succeeds_for_admin(client, admin_headers):
    r = client.post("/admin/packs/import", json={"pack_dir": "packs/ae-con-q0602"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["qp_code"] == "CON/Q0602"
    assert body["nos_count"] == 8
    assert body["pc_count"] == 119
    assert body["task_count"] == 5


def test_pack_import_rejects_path_outside_repo(client, admin_headers):
    r = client.post("/admin/packs/import", json={"pack_dir": "../../etc"}, headers=admin_headers)
    assert r.status_code == 400


def test_pack_import_rejects_missing_directory(client, admin_headers):
    r = client.post("/admin/packs/import", json={"pack_dir": "packs/does-not-exist"}, headers=admin_headers)
    assert r.status_code == 404
