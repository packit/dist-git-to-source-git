# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
import os
import subprocess
from pathlib import Path

import pytest

from tests.conftest import (
    MOCK_BUILD,
    TEST_PROJECTS_WITH_BRANCHES,
    TEST_PROJECTS_WITH_BRANCHES_SINGLE_COMMIT,
    run_dist2src,
    run_packit,
    clone_package,
)


def convert_repo(package_name, dist_git_path, sg_path, branch="c8s"):
    clone_package(package_name, str(dist_git_path), branch=branch)
    run_dist2src(
        ["-vvv", "convert", f"{dist_git_path}:{branch}", f"{sg_path}:{branch}"]
    )


@pytest.mark.parametrize(
    "package_name,branch",
    TEST_PROJECTS_WITH_BRANCHES + TEST_PROJECTS_WITH_BRANCHES_SINGLE_COMMIT,
)
def test_conversions(tmp_path: Path, package_name, branch):
    dist_git_path = tmp_path / "d" / package_name
    sg_path = tmp_path / "s" / package_name
    dist_git_path.mkdir(parents=True)
    sg_path.mkdir(parents=True)
    convert_repo(package_name, dist_git_path, sg_path, branch=branch)
    os.chdir(sg_path)

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
