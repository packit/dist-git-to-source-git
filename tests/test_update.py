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


def test_update_apr(tmp_path: Path):
    """
    Jirka found an issue that we cannot update several packages
    which were created by an old version of d2s, one of them is apr
    """
    package_name = "apr"
    dist_git_path = tmp_path / "d" / package_name
    dg_branch = "c8s"
    source_git_path = tmp_path / "s" / package_name
    sg_branch = "c8"
    clone_package(package_name, str(dist_git_path), branch=dg_branch)
    clone_package(
        package_name,
        str(source_git_path),
        branch=sg_branch,
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
