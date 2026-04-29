from pathlib import Path

import pytest
from repolens.services.ingestion import RepositoryCloner


def test_remote_clone_raises_helpful_error_when_git_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cloner = RepositoryCloner(tmp_path)

    def _raise_missing_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr("subprocess.run", _raise_missing_git)

    with pytest.raises(RuntimeError, match="Git is not installed in the RepoLens runtime"):
        cloner.prepare("https://github.com/example/project")
