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
)


@pytest.mark.parametrize("package_name,branch", TEST_PROJECTS_WITH_BRANCHES)
def test_update(tmp_path: Path, package_name, branch):
    dist_git_path = tmp_path / "d" / package_name
    sg_path = tmp_path / "s" / package_name
    dist_git_path.mkdir(parents=True)
    sg_path.mkdir(parents=True)

    subprocess.check_call(
        [
            "git",
            "clone",
            "-b",
            branch,
            f"https://git.centos.org/rpms/{package_name}.git",
            dist_git_path,
        ]
    )
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

    run_dist2src(["-vvv", "update", f"{dist_git_path}:{branch}", f"{sg_path}:{branch}"])

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
                "--rpmbuild-opts=-bp",
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
    dist_git_path = tmp_path / "d" / package_name
    sg_path = tmp_path / "s" / package_name
    dist_git_path.mkdir(parents=True)
    sg_path.mkdir(parents=True)

    subprocess.check_call(
        [
            "git",
            "clone",
            "-b",
            branch,
            f"https://git.centos.org/rpms/{package_name}.git",
            dist_git_path,
        ]
    )

    run_dist2src(
        ["-vvv", "convert", f"{dist_git_path}:{branch}", f"{sg_path}:{branch}"]
    )

    sg_repo = git.Repo(path=sg_path)
    first_round_commits = list(sg_repo.iter_commits("sg-start..HEAD"))

    run_dist2src(["-vvv", "update", f"{dist_git_path}:{branch}", f"{sg_path}:{branch}"])

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
                "--rpmbuild-opts=-bp",
                "--rebuild",
                "-r",
                "centos-stream-x86_64",
                srpm_path,
            ]
        )


@pytest.mark.parametrize(
    "package_name,branch,old_version", [("rpm", "c8s", "imports/c8s/rpm-4.14.2-37.el8")]
)
def test_update_source(tmp_path: Path, package_name, branch, old_version):
    dist_git_path = tmp_path / "d" / package_name
    sg_path = tmp_path / "s" / package_name
    dist_git_path.mkdir(parents=True)
    sg_path.mkdir(parents=True)

    subprocess.check_call(
        [
            "git",
            "clone",
            "-b",
            branch,
            f"https://git.centos.org/rpms/{package_name}.git",
            dist_git_path,
        ]
    )
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

    run_dist2src(["-vvv", "update", f"{dist_git_path}:{branch}", f"{sg_path}:{branch}"])

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
                "--rpmbuild-opts=-bp",
                "--rebuild",
                "-r",
                "centos-stream-x86_64",
                srpm_path,
            ]
        )
