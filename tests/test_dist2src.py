# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
import shutil
import subprocess
from pathlib import Path

import pytest

from dist2src.core import Dist2Src
from tests.conftest import run_dist2src
from dist2src.not_utils import clone_package

this_dir = Path(__file__).parent
data_dir = this_dir / "data"
acl_template = data_dir / "acl"
meanwhile_template = data_dir / "meanwhile"


def fetch_acl_archive(path: Path, archivne_name: str, url_suffix: str):
    """
    fetch the archive once, have it git-ignored so
    we only do a single HTTP query per CI session
    """
    sources_dir = path / "SOURCES"
    sources_dir.mkdir(exist_ok=True, parents=True)
    archive_path = sources_dir / archivne_name
    if archive_path.is_file():
        return
    subprocess.check_call(
        [
            "curl",
            "-sv",  # -s no progress, -v print something
            "-o",
            str(archive_path),
            f"https://git.centos.org/sources/{url_suffix}",
        ],
        cwd=path,
    )


@pytest.fixture()
def acl(tmp_path: Path):
    dist_git_root = tmp_path / "d" / "acl"
    fetch_acl_archive(
        path=acl_template,
        archivne_name="acl-2.2.53.tar.gz",
        url_suffix="acl/c8/6c9e46602adece1c2dae91ed065899d7f810bf01",
    )
    acl_path = shutil.copytree(acl_template, dist_git_root)
    subprocess.check_call(["git", "init", "."], cwd=acl_path)
    subprocess.check_call(["git", "add", "."], cwd=acl_path)
    subprocess.check_call(["git", "commit", "-m", "Initial import"], cwd=acl_path)
    return acl_path


@pytest.fixture()
def meanwhile(tmp_path: Path):
    dist_git_root = tmp_path / "d" / "meanwhile"
    fetch_acl_archive(
        path=meanwhile_template,
        archivne_name="meanwhile-1.1.0.tar.gz",
        url_suffix="meanwhile/c8/e0e82449ecde20e7499b56ac04eeaf6a2156c1ce",
    )
    acl_path = shutil.copytree(meanwhile_template, dist_git_root)
    subprocess.check_call(["git", "init", "."], cwd=acl_path)
    subprocess.check_call(["git", "add", "."], cwd=acl_path)
    subprocess.check_call(["git", "commit", "-m", "Initial import"], cwd=acl_path)
    return acl_path


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


def test_run_prep(acl):
    run_dist2src(["-v", "run-prep", str(acl)], working_dir=acl)

    assert acl.joinpath("BUILD").is_dir()
    assert acl.joinpath("BUILD").joinpath("acl-2.2.53").is_dir()
    assert acl.joinpath("BUILD").joinpath("acl-2.2.53").joinpath(".git").is_dir()


def test_copy_unapplied_patches(acl):
    run_dist2src(["-v", "run-prep", str(acl)], working_dir=acl)
    d2s = Dist2Src(dist_git_path=acl, source_git_path=None)
    d2s.copy_conditional_patches()


def test_meanwhile_is_right(meanwhile):
    run_dist2src(["-v", "run-prep", str(meanwhile)], working_dir=meanwhile)
    """
Patch0:         %{name}-crash.patch
Patch1:         %{name}-
Patch2:         %{name}-
Patch3:         %{name}-
# https://bugzilla.redhat.com/show_bug.cgi?id=1037196
Patch4:         %{name}
    """
    patches = (
        (b"meanwhile-format-security-fix.patch", False),
        (b"meanwhile-status-timestamp-workaround.patch", False),
        (b"meanwhile-file-transfer.patch", False),
        (b"meanwhile-fix-glib-headers.patch", False),
        (b"meanwhile-crash.patch", True),
    )
    for idx in range(5):
        commit_content = subprocess.check_output(
            ["git", "show", "HEAD" + "^" * idx],
            cwd=str(meanwhile / "BUILD/meanwhile-1.1.0"),
        )
        assert patches[idx][0] in commit_content
        if patches[idx][1]:
            assert b"no_prefix: true" in commit_content
        else:
            assert b"no_prefix:" not in commit_content


def test_no_backup(tmp_path: Path):
    package_name = "hyperv-daemons"
    d = tmp_path / "d"
    d.mkdir()
    dist_git_path = d / package_name
    clone_package(package_name, str(dist_git_path), branch="c8")
    b = dist_git_path / "BUILD" / "hyperv-daemons-0"
    run_dist2src(["-v", "run-prep", str(dist_git_path)], working_dir=dist_git_path)
    assert b.is_dir()
    assert b.joinpath("lsvmbus").is_file()
    assert not b.joinpath("lsvmbus.lsvmbus_python3").exists()
