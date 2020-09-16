# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
import os
from pathlib import Path

from click.testing import CliRunner

from dist2src.cli import cli
from packit.cli.packit_base import packit_base
from packit.utils import cwd

TEST_PROJECTS_WITH_BRANCHES = [
    ("rpm", "c8s"),  # %autosetup and lots of patches
    ("drpm", "c8s"),  # easy
    # %autosetup -S git_am + needs https://koji.mbox.centos.org/koji/taginfo?tagID=342
    ("pacemaker", "c8s"),
    ("systemd", "c8s"),  # -S git_am
    # ("kernel", "c8s"),  # !!!
    # (
    #    "qemu-kvm",
    #    "c8s-stream-rhel",
    # ),  # %setup -q -n qemu-%{version} + %autopatch -p1
    # (
    #    "libvirt",
    #    "c8s-stream-rhel",
    # ),  # %autosetup -S git_am -N + weirdness + %autopatch
    # ( "libreport", "c8s")  # -S git, they redefine "__scm_apply_git"
    ("autofs", "c8s"),
    ("NetworkManager", "c8s"),
    ("dnf", "c8s"),
    ("podman", "c8s-stream-rhel8"),
    # alsa-lib has an empty patch file, we need support in packit for that
    # https://bugzilla.redhat.com/show_bug.cgi?id=1875768
    # https://github.com/packit/packit/issues/957
    # ("alsa-lib", "c8s"),
    # no %prep lol, https://github.com/packit/dist-git-to-source-git/issues/46
    # ("appstream-data", "c8s"),
    ("apr", "c8s"),
    ("arpwatch", "c8s"),
    # ("atlas", "c8s")  # insanity + requires lapack-devel to be present while converting
    ("bind", "c8s"),
    ("boom-boot", "c8s"),
    ("boost", "c8s"),  # %setup + find + %patch
    # ("google-noto-cjk-fonts", "c8s")  # archive 1.8G, repo ~4G
    ("python-rpm-generators", "c8s"),  # keine upstream archive, luckily %autosetup
]

TEST_PROJECTS_WITH_BRANCHES_SINGLE_COMMIT = [
    (
        "HdrHistogram_c",
        "c8s",
    ),  # eaaaaasy
    ("units", "c8"),  # autosetup + files created during %prep
    ("vhostmd", "c8s"),  # -S git, eazy
    ("autogen", "c8s"),
    ("acpica-tools", "c8"),
    ("socat", "c8s"),  # %setup + %patch # problem with  previous commit
]


MOCK_BUILD = bool(os.environ.get("MOCK_BUILD"))


def run_dist2src(*args, working_dir=None, **kwargs):
    working_dir = working_dir or Path.cwd()
    with cwd(working_dir):
        cli_runner = CliRunner()
        cli_runner.invoke(cli, *args, catch_exceptions=False, **kwargs)


def run_packit(*args, working_dir=None, **kwargs):
    working_dir = working_dir or Path.cwd()
    with cwd(working_dir):
        cli_runner = CliRunner()
        cli_runner.invoke(packit_base, *args, catch_exceptions=False, **kwargs)
