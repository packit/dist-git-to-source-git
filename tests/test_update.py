# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import subprocess
from pathlib import Path

import git
import pytest

from tests.conftest import (
    MOCK_BUILD,
    TEST_PROJECTS_WITH_BRANCHES,
    TEST_PROJECTS_WITH_BRANCHES_SINGLE_COMMIT,
    run_dist2src,
    run_packit,
    clone_package,
)


@pytest.mark.parametrize("package_name,branch", TEST_PROJECTS_WITH_BRANCHES)
def test_update(tmp_path: Path, package_name, branch):
    """
    perform an update from a previous dist-git commit (HEAD~1)
    to the last one (HEAD)
    """
    dist_git_path = tmp_path / "d" / package_name
    sg_path = tmp_path / "s" / package_name
    dist_git_path.mkdir(parents=True)
    sg_path.mkdir(parents=True)

    clone_package(package_name, str(dist_git_path), branch=branch)
    subprocess.check_call(
        ["git", "reset", "--hard", "HEAD~1"],
        cwd=dist_git_path,
    )

    run_dist2src(
        ["-vvv", "convert", f"{dist_git_path}:{branch}", f"{sg_path}:{branch}"]
    )

    subprocess.check_call(
        ["git", "pull", "origin", branch],
        cwd=dist_git_path,
    )

    run_dist2src(
        ["-vvv", "convert", f"{dist_git_path}:{branch}", f"{sg_path}:{branch}"]
    )

    run_packit(
        [
            "--debug",
            "srpm",
        ],
        working_dir=sg_path,  # _srcrpmdir rpm macro is set to /, let's CWD then
    )
    srpm_path = next(sg_path.glob("*.src.rpm"))
    assert srpm_path.exists()
    if MOCK_BUILD:
        subprocess.check_call(
            [
                "mock",
                "--rebuild",
                "-r",
                "centos-stream-x86_64",
                srpm_path,
            ]
        )


@pytest.mark.parametrize(
    "package_name,branch", TEST_PROJECTS_WITH_BRANCHES_SINGLE_COMMIT
)
def test_update_from_same_commit(tmp_path: Path, package_name, branch):
    """
    run an update twice from the same commit
    """
    dist_git_path = tmp_path / "d" / package_name
    sg_path = tmp_path / "s" / package_name
    dist_git_path.mkdir(parents=True)
    sg_path.mkdir(parents=True)

    clone_package(package_name, str(dist_git_path), branch=branch)

    run_dist2src(
        ["-vvv", "convert", f"{dist_git_path}:{branch}", f"{sg_path}:{branch}"]
    )

    sg_repo = git.Repo(path=sg_path)
    first_round_commits = list(sg_repo.iter_commits("sg-start..HEAD"))

    run_dist2src(
        ["-vvv", "convert", f"{dist_git_path}:{branch}", f"{sg_path}:{branch}"]
    )

    second_round_commits = list(sg_repo.iter_commits("sg-start..HEAD"))

    run_packit(
        [
            "--debug",
            "srpm",
            "--output",
            str(sg_path / f"{package_name}.src.rpm"),
            str(sg_path),
        ]
    )
    srpm_path = next(sg_path.glob("*.src.rpm"))
    assert srpm_path.exists()

    # Check that patch commits are same
    assert len(first_round_commits) == len(second_round_commits)
    for first, second in zip(first_round_commits, second_round_commits):
        assert b"" == subprocess.check_output(
            ["git", "-C", str(sg_path), "diff", first.hexsha, second.hexsha]
        )

    if MOCK_BUILD:
        subprocess.check_call(
            [
                "mock",
                "--rebuild",
                "-r",
                "centos-stream-x86_64",
                srpm_path,
            ]
        )


@pytest.mark.parametrize(
    "package_name,branch,old_version",
    [
        ("rpm", "c8s", "imports/c8s/rpm-4.14.2-37.el8"),
        ("systemd", "c8s", "imports/c8/systemd-239-13.el8_0.3"),
    ],
)
def test_update_source(tmp_path: Path, package_name, branch, old_version):
    """ perform an update from a specific ref to the last commit """
    dist_git_path = tmp_path / "d" / package_name
    sg_path = tmp_path / "s" / package_name
    dist_git_path.mkdir(parents=True)
    sg_path.mkdir(parents=True)

    clone_package(package_name, str(dist_git_path), branch=branch)
    subprocess.check_call(
        ["git", "reset", "--hard", old_version],
        cwd=dist_git_path,
    )

    run_dist2src(
        ["-vvv", "convert", f"{dist_git_path}:{branch}", f"{sg_path}:{branch}"]
    )

    subprocess.check_call(
        ["git", "pull", "origin", branch],
        cwd=dist_git_path,
    )

    run_dist2src(
        ["-vvv", "convert", f"{dist_git_path}:{branch}", f"{sg_path}:{branch}"]
    )

    run_packit(
        [
            "--debug",
            "srpm",
            "--output",
            str(sg_path / f"{package_name}.src.rpm"),
            str(sg_path),
        ]
    )
    srpm_path = next(sg_path.glob("*.src.rpm"))
    assert srpm_path.exists()
    if MOCK_BUILD:
        subprocess.check_call(
            [
                "mock",
                "--rebuild",
                "-r",
                "centos-stream-x86_64",
                srpm_path,
            ]
        )


@pytest.mark.parametrize(
    "package",
    (
        "apr",
        "meson",
        "ostree",
        "pacemaker",
        "vala",
        "upower",
    ),
)
def test_update_existing(tmp_path: Path, package):
    """
    Jirka found an issue that we cannot update several packages
    which were created by an old version of d2s, one of them is apr
    """
    dist_git_path = tmp_path / "d" / package
    dg_branch = "c8s"
    source_git_path = tmp_path / "s" / package
    sg_branch = "c8s"
    clone_package(package, str(dist_git_path), branch=dg_branch)
    clone_package(
        package,
        str(source_git_path),
        branch="master",
        namespace="source-git",
        stg=True,
    )
    run_dist2src(
        [
            "-vvv",
            "convert",
            f"{dist_git_path}:{dg_branch}",
            f"{source_git_path}:{sg_branch}",
        ]
    )
    run_packit(
        [
            "--debug",
            "srpm",
        ],
        working_dir=source_git_path,
    )
    srpm_path = next(source_git_path.glob("*.src.rpm"))
    assert srpm_path.exists()


def test_update_catch(tmp_path: Path):
    """
    make sure we can update package catch and
    check the repo is in expected state after the update
    """
    package = "catch"
    dist_git_path = tmp_path / "d" / package
    dg_branch = "c8"
    source_git_path = tmp_path / "s" / package
    sg_branch = "c8"
    clone_package(package, str(dist_git_path), branch=dg_branch)
    clone_package(
        package,
        str(source_git_path),
        branch="master",
        namespace="source-git",
        stg=True,
    )
    run_dist2src(
        [
            "-vvv",
            "convert",
            f"{dist_git_path}:{dg_branch}",
            f"{source_git_path}:{sg_branch}",
        ]
    )
    run_packit(
        [
            "--debug",
            "srpm",
        ],
        working_dir=source_git_path,
    )
    srpm_path = next(source_git_path.glob("*.src.rpm"))
    assert srpm_path.exists()
    git_log_out = subprocess.check_output(
        ["git", "log", "--pretty=format:%s", "origin/c8.."], cwd=source_git_path
    ).decode()
    # the line below is really fragile
    # if it breaks, navigate to the source-git repo and check git history
    assert (
        git_log_out
        == """Changes after running %prep
Add sources defined in the spec file
Add spec-file for the distribution
.packit.yaml
catch-2.2.1 base
Prepare for a new update"""
    )
