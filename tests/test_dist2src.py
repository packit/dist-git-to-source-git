# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dist2src.core import Dist2Src

this_dir = Path(__file__).parent
data_dir = this_dir / "data"
acl_template = data_dir / "acl"


def run_prep(dist_git_path: Path):
    make_env = os.environ.copy()
    make_cmd = ["make", "run"]
    container_dg_p = f"/d/{dist_git_path.name}"
    make_env.update(
        {
            "OPTS": (f"-v {dist_git_path}:{container_dg_p}:rw,Z "),
            "CONTAINER_CMD": (f"dist2src -v run-prep {container_dg_p}"),
        }
    )

    subprocess.check_call(make_cmd, env=make_env)


def fetch_acl_archive(path: Path):
    """
    fetch the archive once, have it git-ignored so
    we only do a single HTTP query per CI session
    """
    sources_dir = path / "SOURCES"
    sources_dir.mkdir(exist_ok=True, parents=True)
    archive_path = sources_dir / "acl-2.2.53.tar.gz"
    if archive_path.is_file():
        return
    subprocess.check_call(
        [
            "curl",
            "-sv",  # -s no progress, -v print something
            "-o",
            str(archive_path),
            "https://git.centos.org/sources/acl/c8/6c9e46602adece1c2dae91ed065899d7f810bf01",
        ],
        cwd=path,
    )


@pytest.fixture()
def acl(tmp_path: Path):
    dist_git_root = tmp_path / "d" / "acl"
    fetch_acl_archive(path=acl_template)
    acl_path = shutil.copytree(acl_template, dist_git_root)
    subprocess.check_call(["git", "init", "."], cwd=acl_path)
    subprocess.check_call(["git", "add", "."], cwd=acl_path)
    subprocess.check_call(["git", "commit", "-m", "Initial import"], cwd=acl_path)
    return acl_path


def test_run_prep(acl):
    run_prep(acl)

    assert acl.joinpath("BUILD").is_dir()
    assert acl.joinpath("BUILD").joinpath("acl-2.2.53").is_dir()
    assert acl.joinpath("BUILD").joinpath("acl-2.2.53").joinpath(".git").is_dir()


# you cannot use fixtures in parametrize
@pytest.mark.parametrize(
    "set_dist,set_src,expected",
    (
        (True, True, "acl"),
        (True, None, "acl"),
        (None, True, "acl"),
    ),
)
def test_pkg_name(acl, set_dist, set_src, expected):
    dist_path, src_path = None, None
    if set_dist:
        dist_path = acl
    if set_src:
        src_path = acl
    assert (
        Dist2Src(dist_git_path=dist_path, source_git_path=src_path).package_name
        == expected
    )


def test_pkg_name_when_paths_not_set():
    with pytest.raises(RuntimeError) as exc:
        assert not Dist2Src(dist_git_path=None, source_git_path=None).package_name
    assert "I'm sorry but nor dist_git_path nor source_git_path are defined." in str(
        exc
    )
