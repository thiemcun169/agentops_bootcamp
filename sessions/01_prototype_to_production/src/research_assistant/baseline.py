"""Baseline smoke run: a fixed input, plus everything needed to rebuild the same release, saved to baselines/."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from research_assistant.agent import ask
from research_assistant.config import PROMPT_FILE, Settings

BASELINE_DIR = Path("baselines")
INPUT_FILE = BASELINE_DIR / "input.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None  # not a git repository yet


def manifest(settings: Settings) -> dict:
    """The input side of the baseline: which code, dependencies, model, prompt and config produced it."""
    return {
        "package_version": version("research-assistant"),
        "git_describe": _git("describe", "--tags", "--always", "--dirty"),
        "git_commit": _git("rev-parse", "--short", "HEAD"),
        "uv_lock_sha256": _sha256(Path("uv.lock")),
        "prompt_sha256": _sha256(PROMPT_FILE),
        "model": settings.model,
        "config": {"app_env": settings.app_env, "max_search_results": settings.max_search_results},
    }


def run_baseline(settings: Settings) -> Path:
    question = json.loads(INPUT_FILE.read_text(encoding="utf-8"))["question"]
    record = {"manifest": manifest(settings), "input": question, **ask(question, settings)}
    record["created_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    release = record["manifest"]["git_describe"] or f"v{record['manifest']['package_version']}"
    out = BASELINE_DIR / release / f"run_{record['created_at'].replace(':', '')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
