from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sensitive_runtime_artifacts_and_real_data_are_ignored():
    patterns = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert {
        ".env",
        "traces/",
        "pilot_sessions/",
        "participant_data/",
        "raw_audio/",
        "backend/data/olist/",
        "datasets/olist/data/",
        "node_modules/",
        "dist/",
    } <= patterns
