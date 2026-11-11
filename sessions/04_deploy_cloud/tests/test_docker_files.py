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


def test_healthcheck_follows_the_port_variable():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "os.environ.get('PORT', '8000')" in dockerfile  # Cloud Run sets PORT=8080; the local check must follow it
    assert "127.0.0.1:8000" not in dockerfile


def test_deploy_files_hold_no_secret_and_stay_out_of_git():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "deploy/cloudrun.env" in ignored and "secrets/" in ignored
    example = (ROOT / "deploy" / "cloudrun.env.example").read_text(encoding="utf-8")
    assert "API_KEY" not in example and "PASSWORD" not in example
