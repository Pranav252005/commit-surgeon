import re
from pathlib import Path

import yaml
from typer.testing import CliRunner

from surgeon.cli import app

ROOT = Path(__file__).parent.parent


def test_action_is_a_valid_composite_and_uses_real_cli_flags():
    action = yaml.safe_load((ROOT / "action/action.yml").read_text())
    assert action["runs"]["using"] == "composite"
    scripts = "\n".join(s.get("run", "") for s in action["runs"]["steps"])
    help_text = CliRunner().invoke(app, ["analyze", "--help"], terminal_width=200).output
    flags = set(re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", scripts))
    cli_flags = {f for f in flags if f in {"--quiet", "--md", "--json", "--no-model", "--base-url", "--model", "--api-key-env"}}
    assert cli_flags, "the action should call analyze with flags"
    missing = [f for f in cli_flags if f not in help_text]
    assert not missing, f"action uses flags the CLI does not have: {missing}"
    for name in ("verdict", "score"):
        assert name in action["outputs"]


def test_action_never_echoes_the_api_key():
    text = (ROOT / "action/action.yml").read_text()
    assert "echo $SURGEON_API_KEY" not in text and "echo \"$SURGEON_API_KEY\"" not in text
    assert "--api-key-env SURGEON_API_KEY" in text  # the name of the variable, never its value


def test_example_workflow_parses_and_grants_only_what_it_needs():
    wf = yaml.safe_load((ROOT / "examples/surgeon.yml").read_text())
    assert wf["permissions"] == {"contents": "read", "pull-requests": "write"}
