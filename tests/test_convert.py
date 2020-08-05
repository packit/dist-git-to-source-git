#!/usr/bin/python3

# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
import os
import subprocess
from pathlib import Path

import pytest


def convert_repo(package_name, dist_git_path, sg_path):
    subprocess.check_call(
        [
            "git",
            "clone",
            "-b",
            "c8s",
            f"https://git.centos.org/rpms/{package_name}.git",
            dist_git_path,
        ]
    )
    make_env = os.environ.copy()
    make_cmd = ["make", "run"]
    container_sg_p = f"/s/{package_name}"
    container_dg_p = f"/d/{package_name}"
    make_env.update(
        {
            "OPTS": (
                f"-v {dist_git_path}:{container_dg_p}:rw "
                f"-v {sg_path}:{container_sg_p}:rw --workdir /"
            ),
            "CONTAINER_CMD": (
                f"dist2src -vv convert-with-prep "
                f"{container_dg_p}:c8s {container_sg_p}:c8s"
            ),
        }
    )

    subprocess.check_call(make_cmd, env=make_env)


@pytest.mark.parametrize(
    "package_name",
    (
        "rpm",
        "drpm",
        "HdrHistogram_c"
        # "kernel"  one day
    ),
)
def test_conversions(tmp_path: Path, package_name):
    dist_git_path = tmp_path / "d" / package_name
    sg_path = tmp_path / "s" / package_name
    dist_git_path.mkdir(parents=True)
    sg_path.mkdir(parents=True)
    convert_repo(package_name, dist_git_path, sg_path)
    subprocess.check_call(["packit", "srpm"], cwd=sg_path)
    srpm_path = next(sg_path.glob("*.src.rpm"))
    assert srpm_path.exists()
    subprocess.check_call(
        ["mock", "--rebuild", "-r", "centos-stream-x86_64", srpm_path]
    )
