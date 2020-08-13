#!/usr/bin/python3

# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
import os
import subprocess
from pathlib import Path

import pytest


def convert_repo(package_name, dist_git_path, sg_path, branch="c8s"):
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
                f"dist2src -v convert-with-prep "
                f"{container_dg_p}:{branch} {container_sg_p}:{branch}"
            ),
        }
    )

    subprocess.check_call(make_cmd, env=make_env)


@pytest.mark.parametrize(
    "package_name,branch",
    (
        ("rpm", "c8s"),  # %autosetup and lots of patches
        ("drpm", "c8s"),  # easy
        ("HdrHistogram_c", "c8s"),  # eaaaaasy
        ("units", "c8"),  # autosetup + files created during %prep
        # %autosetup -S git_am + needs https://koji.mbox.centos.org/koji/taginfo?tagID=342
        # "pacemaker",
        # ("systemd", "c8s"),  # -S git_am
        # ("kernel", "c8s"),  # !!!
        (
            "qemu-kvm",
            "c8s-stream-rhel",
        ),  # %setup -q -n qemu-%{version} + %autopatch -p1
        (
            "libvirt",
            "c8s-stream-rhel",
        ),  # %autosetup -S git_am -N + weirdness + %autopatch
    ),
)
def test_conversions(tmp_path: Path, package_name, branch):
    dist_git_path = tmp_path / "d" / package_name
    sg_path = tmp_path / "s" / package_name
    dist_git_path.mkdir(parents=True)
    sg_path.mkdir(parents=True)
    convert_repo(package_name, dist_git_path, sg_path, branch=branch)
    subprocess.check_call(["packit", "--debug", "srpm"], cwd=sg_path)
    srpm_path = next(sg_path.glob("*.src.rpm"))
    assert srpm_path.exists()
    # we don't care about the build itself, mainly that patches are applied correctly, hence -bp
    return
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
