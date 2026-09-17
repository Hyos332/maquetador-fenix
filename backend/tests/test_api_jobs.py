from pathlib import Path

from fastapi.testclient import TestClient

from app.api import routes
from app.config.settings import Settings
from app.main import app

ALBERTO_FIXTURE = Path("/home/luis.hoyos@ctdesarrollo-sdr.org/Descargas/Alberto Nilson.zip")


def test_api_creates_job_and_exposes_outputs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "app_settings",
        Settings(
            workspaces_dir=tmp_path / "workspaces",
            deliveries_dir=tmp_path / "deliveries",
            dry_run=True,
        ),
    )
    routes.jobs.clear()

    client = TestClient(app)
    with ALBERTO_FIXTURE.open("rb") as file:
        response = client.post(
            "/api/jobs",
            files={"file": ("Alberto Nilson.zip", file, "application/zip")},
        )

    assert response.status_code == 200
    job_id = response.json()["job_id"]

    status_response = client.get(f"/api/jobs/{job_id}")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["doi"] == "10.60134/mlshn.v5n1.4594"
    assert payload["references_count"] == 175
    assert payload["abstract_es_word_count"] > payload["abstract_word_limit"]
    assert payload["html_url"] == f"/api/jobs/{job_id}/html"
    assert payload["epub_url"] == f"/api/jobs/{job_id}/epub"
    assert payload["delivery_url"] == f"/api/jobs/{job_id}/delivery"

    assert client.get(payload["html_url"]).status_code == 200
    assert client.get(payload["epub_url"]).status_code == 200
    assert client.get(payload["delivery_url"]).status_code == 200
    assert client.get(f"/api/jobs/{job_id}/galleys.css").status_code == 200
    assert client.get(f"/api/jobs/{job_id}/Figure_1.PNG").status_code == 200

    review_response = client.patch(
        f"/api/jobs/{job_id}/abstracts",
        json={"abstract_es": "Resumen revisado por una persona, sin cambiar la intención científica."},
    )
    assert review_response.status_code == 200

    reviewed_payload = client.get(f"/api/jobs/{job_id}").json()
    assert reviewed_payload["abstract_es_word_count"] <= reviewed_payload["abstract_word_limit"]
    assert not any("Resumen has" in warning for warning in reviewed_payload["warnings"])
    assert client.get(reviewed_payload["html_url"]).status_code == 200
