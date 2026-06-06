import os
import subprocess
from pathlib import Path


def test_shell_load_env_sets_missing_values_without_overwriting_existing(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("A=from_file\nB='two words'\nexport C=three\nBAD-LINE=x\n# ignored\n", encoding="utf-8")
    helper = Path(__file__).resolve().parents[1] / "scripts" / "load_env.sh"

    script = f"""
set -euo pipefail
A=existing
export A
source {helper} {env_file}
printf '%s|%s|%s|%s\n' "$A" "$B" "$C" "${{BAD_LINE:-unset}}"
"""
    env = os.environ.copy()
    env.pop("B", None)
    env.pop("C", None)
    env.pop("BAD_LINE", None)
    result = subprocess.run(["bash", "-c", script], text=True, capture_output=True, check=True, env=env)

    assert result.stdout.strip() == "existing|two words|three|unset"


def test_shell_load_env_ignores_missing_file():
    helper = Path(__file__).resolve().parents[1] / "scripts" / "load_env.sh"

    script = f"""
set -euo pipefail
source {helper} /tmp/definitely-missing-qq-hermes-env
printf 'ok\n'
"""
    result = subprocess.run(["bash", "-c", script], text=True, capture_output=True, check=True)

    assert result.stdout.strip() == "ok"
