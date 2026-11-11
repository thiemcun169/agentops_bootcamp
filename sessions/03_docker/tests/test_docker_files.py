"""Offline checks of the container files: no Docker daemon needed."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cmd_is_exec_form_and_runs_as_non_root():
    lines = (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
    assert 'CMD ["fastapi", "run"]' in lines  # exec form: fastapi is PID 1 and gets SIGTERM
    assert "USER app" in lines


def test_secrets_stay_out_of_the_build_context():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in ignored and ".env.*" in ignored and "venvAO*" in ignored
    assert "data/" not in ignored and "README.md" not in ignored  # the API reads data/users.json; uv_build needs README


def test_compose_reaches_postgres_by_service_name():
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "DB_HOST: postgres" in compose and "condition: service_healthy" in compose
