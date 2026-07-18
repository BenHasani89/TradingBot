import subprocess
from unittest.mock import patch

from tradingbot.research_tracking.versioning import current_git_commit


def test_current_git_commit_returns_string_or_none_in_real_repo():

    commit = current_git_commit()

    assert commit is None or (isinstance(commit, str) and len(commit) == 40)


def test_current_git_commit_returns_none_when_git_missing():

    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert current_git_commit() is None


def test_current_git_commit_returns_none_on_nonzero_exit():

    class _Result:
        returncode = 128
        stdout = ""

    with patch("subprocess.run", return_value=_Result()):
        assert current_git_commit() is None


def test_current_git_commit_returns_none_on_timeout():

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5)):
        assert current_git_commit() is None


def test_current_git_commit_never_raises_on_unexpected_oserror():

    with patch("subprocess.run", side_effect=OSError("unerwarteter Fehler")):
        assert current_git_commit() is None


def test_current_git_commit_strips_whitespace():

    class _Result:
        returncode = 0
        stdout = "abc123\n"

    with patch("subprocess.run", return_value=_Result()):
        assert current_git_commit() == "abc123"


def test_current_git_commit_empty_output_is_none():

    class _Result:
        returncode = 0
        stdout = "   \n"

    with patch("subprocess.run", return_value=_Result()):
        assert current_git_commit() is None
