# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import subprocess
from pathlib import Path
from click.testing import CliRunner

import pytest

from dist2src.cli import cli
from packit.cli.packit_base import packit_base
from packit.utils import cwd


def run_dist2src(*args, working_dir=None, **kwargs):
    working_dir = working_dir or Path()
    with cwd(working_dir):
        cli_runner = CliRunner()
        cli_runner.invoke(cli, *args, catch_exceptions=False, **kwargs)


def run_packit(*args, **kwargs):
    cli_runner = CliRunner()
    cli_runner.invoke(packit_base, *args, catch_exceptions=False, **kwargs)


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
    run_dist2src(
        ["-vvv", "convert", f"{dist_git_path}:{branch}", f"{sg_path}:{branch}"]
    )


@pytest.mark.parametrize(
    "package_name,branch",
    (
        ("rpm", "c8s"),  # %autosetup and lots of patches
        ("drpm", "c8s"),  # easy
        ("HdrHistogram_c", "c8s"),  # eaaaaasy
        ("units", "c8"),  # autosetup + files created during %prep
        # %autosetup -S git_am + needs https://koji.mbox.centos.org/koji/taginfo?tagID=342
        ("pacemaker", "c8s"),
        ("systemd", "c8s"),  # -S git_am
        # ("kernel", "c8s"),  # !!!
        (
            "qemu-kvm",
            "c8s-stream-rhel",
        ),  # %setup -q -n qemu-%{version} + %autopatch -p1
        (
            "libvirt",
            "c8s-stream-rhel",
        ),  # %autosetup -S git_am -N + weirdness + %autopatch
        # ( "libreport", "c8s")  # -S git, they redefine "__scm_apply_git"
        ("socat", "c8s"),  # %setup + %patch
        ("vhostmd", "c8s"),  # -S git, eazy
        ("autogen", "c8s"),
        ("autofs", "c8s"),
    ),
)
def test_conversions(tmp_path: Path, package_name, branch):
    dist_git_path = tmp_path / "d" / package_name
    sg_path = tmp_path / "s" / package_name
    dist_git_path.mkdir(parents=True)
    sg_path.mkdir(parents=True)
    convert_repo(package_name, dist_git_path, sg_path, branch=branch)

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
    # TODO: implement `packit prep` and run it here
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
