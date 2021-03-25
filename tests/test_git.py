# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
from pathlib import Path

from dist2src.core import GitRepo


def test_is_file_tracked(tmp_path: Path):
    g = GitRepo(tmp_path, create=True)
    (g.repo_path / "file").write_text("asd")
    g.stage("file")
    g.commit("stuff")
    assert g.is_file_tracked("file")
    assert not g.is_file_tracked("file2")
