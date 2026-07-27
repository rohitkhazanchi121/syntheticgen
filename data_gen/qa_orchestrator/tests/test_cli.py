import subprocess
import pytest

def test_cli():
    """
    Verify the CLI entry point works.
    We just check if it runs help successfully.
    """
    result = subprocess.run(
        ["qa-orchestrator", "--help"],
        capture_output=True,
        text=True
    )
    # Since we are wrapping pytest, --help should show pytest help
    assert result.returncode == 0
    assert "pytest" in result.stdout or "usage:" in result.stdout
