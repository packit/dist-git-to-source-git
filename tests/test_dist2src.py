# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
import shutil
import subprocess
from pathlib import Path

import pytest
import requests
from flexmock import flexmock
from requests import Response

from dist2src.core import Dist2Src
from tests.conftest import clone_package, run_dist2src

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


@pytest.mark.parametrize(
    "package,branch",
    (
        ("acl", "c8"),
        ("meanwhile", "c8s"),
    ),
)
def test_get_lookaside_sources(tmp_path: Path, package, branch):
    d = tmp_path / "d"
    s = tmp_path / "s"
    d.mkdir()
    s.mkdir()
    dist_git_path = d / package
    source_git_path = s / package
    clone_package(package, str(dist_git_path), branch=branch)

    d2s = Dist2Src(dist_git_path=dist_git_path, source_git_path=source_git_path)
    sources = d2s.get_lookaside_sources(branch)
    d2s.copy_all_sources()

    (source_git_path / "SPECS").mkdir(exist_ok=True)
    for source_dict in sources:
        response = requests.get(source_dict["url"])
        # make sure we haven't copied sources which are in lookaside
        assert not Path(source_dict["path"]).exists()
        source_git_path.joinpath(source_dict["path"]).write_bytes(response.content)


def test_gitlab_ci_config_removed(tmp_path: Path):
    package = "libssh"
    d = tmp_path / "d"
    s = tmp_path / "s"
    d.mkdir()
    s.mkdir()
    dist_git_path = d / package
    source_git_path = s / package
    clone_package(package, str(dist_git_path), branch="c8s")
    gitlab_config_name = ".gitlab-ci.yml"

    d2s = Dist2Src(dist_git_path=dist_git_path, source_git_path=source_git_path)
    d2s.fetch_archive()
    # run %prep
    d2s.run_prep(ensure_autosetup=False)

    # make sure the the config file is present
    assert d2s.BUILD_repo_path.joinpath(gitlab_config_name).exists()

    # put %prep output to the source-git repo and commit it
    d2s.move_prep_content()
    d2s.source_git.stage(add=".")
    d2s.source_git.commit(message="commit all")

    # remove the config and verify it's not present
    d2s.remove_gitlab_ci_config()
    assert not d2s.source_git_path.joinpath(gitlab_config_name).exists()


def test_packit_yaml_is_correct(tmp_path: Path):
    d = tmp_path / "d"
    s = tmp_path / "s"
    d.mkdir()
    subprocess.check_call(["git", "init", "."], cwd=d)
    s.mkdir()
    subprocess.check_call(["git", "init", "."], cwd=s)
    (d / ".pkg.metadata").write_text("123456 SOURCES/archive.tar.gz\n")

    ok_response = Response()
    ok_response.reason = ""
    ok_response.status_code = 200
    flexmock(requests).should_receive("head").and_return(ok_response)

    d2s = Dist2Src(dist_git_path=d, source_git_path=s)
    d2s.add_packit_config("U", "c8s", commit=False)

    packit_yaml = s / ".packit.yaml"
    assert packit_yaml.read_text() == (
        "jobs:\n"
        "- job: copr_build\n"
        "  metadata:\n"
        "    targets:\n"
        "    - centos-stream-8-x86_64\n"
        "  trigger: pull_request\n"
        "- job: tests\n"
        "  metadata:\n"
        "    targets:\n"
        "    - centos-stream-8-x86_64\n"
        "  trigger: pull_request\n"
        "sources:\n"
        "- path: archive.tar.gz\n"
        "  url: https://git.centos.org/sources/d/c8s/123456\n"
        "specfile_path: SPECS/d.spec\n"
        "upstream_ref: U\n"
    )
