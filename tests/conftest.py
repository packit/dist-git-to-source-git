# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
import os
from pathlib import Path

from click.testing import CliRunner

from dist2src.cli import cli
from packit.cli.packit_base import packit_base
from packit.utils import cwd

TEST_PROJECTS_WITH_BRANCHES = [
    # %autosetup -S git_am + needs https://koji.mbox.centos.org/koji/taginfo?tagID=342
    ("pacemaker", "c8s"),
    ("systemd", "c8s"),  # -S git_am
    ("kernel", "c8s"),  # !!!
    # (
    #    "qemu-kvm",
    #    "c8s-stream-rhel",
    # ),  # %setup -q -n qemu-%{version} + %autopatch -p1
    # (
    #    "libvirt",
    #    "c8s-stream-rhel",
    # ),  # %autosetup -S git_am -N + weirdness + %autopatch
    ("libreport", "c8s"),  # -S git, they redefine "__scm_apply_git"
    # FIXME: We need packit 0.20 or packit/packit#1000
    # ("podman", "c8s-stream-rhel8"),  # %autosetup -Sgit, tar fx %SOURCE1
    # alsa-lib has an empty patch file, we need support in packit for that
    # https://bugzilla.redhat.com/show_bug.cgi?id=1875768
    # https://github.com/packit/packit/issues/957
    # ("alsa-lib", "c8s"),
    # no %prep lol, https://github.com/packit/dist-git-to-source-git/issues/46
    # ("appstream-data", "c8s"),
    # ("atlas", "c8s")  # insanity + requires lapack-devel to be present while converting
    ("bind", "c8s"),  # %setup, conditional patches, mkdir, cp
    ("boost", "c8s"),  # %setup + find + %patch
    # ("google-noto-cjk-fonts", "c8s")  # archive 1.8G, repo ~4G
    ("python-rpm-generators", "c8s"),  # keine upstream archive, luckily %autosetup
    # big dawg: conditional arch patches, %setup -a 1 -a 2, patching additional archives
    ("gcc", "c8s"),
    ("gdb", "c8s"),  # conditional patching, a ton of if's and addition of more sources
    ("sqlite", "c8s"),  # conditional patching + autoconf
    ("haproxy", "c8s"),  # they ignore our files
    # ("openblas", "c8"),  # openblas-0.3.3/OpenBLAS-0.3.3/
    # ("fuse", "c8"),  # 2 libraries being built in a single buildroot, we cannot make
    #                  # a reliable source-git for this
    (
        "unbound",
        "c8",
    ),  # again, another level of directories and patches applied in a subdir
    ("hyperv-daemons", "c8"),  # no archive, source code is %SOURCEXXX, does not update
]

# these packages only have a single commit in the respective dist-git branch
TEST_PROJECTS_WITH_BRANCHES_SINGLE_COMMIT = [
    ("units", "c8"),  # autosetup + files created during %prep
    ("vhostmd", "c8s"),  # -S git, eazy
    ("acpica-tools", "c8"),  # %setup, %patch, unpack %SOURCE1, a ton of operations
    ("socat", "c8s"),  # %setup + %patch # problem with  previous commit
    ("meanwhile", "c8"),  # -p0 + -p1 patches
    ("nss-util", "c8"),  # double nested dir: nss-util-3.39/nss/ and `cd nss` in %prep
    ("metis", "c8"),  # %setup -qc && pushd %{name}-%{version}
]


MOCK_BUILD = bool(os.environ.get("MOCK_BUILD"))


def run_dist2src(*args, working_dir=None, **kwargs):
    working_dir = working_dir or Path.cwd()
    with cwd(working_dir):
        cli_runner = CliRunner()
        # if you want to run debugger inside you need to do 2 things:
        # get real std{in,out} at the level of imports because click patches it
        # invoke pdb like this: "import pdb; pdb.Pdb(stdin=stdin, stdout=stdout).set_trace()"
        cli_runner.invoke(cli, *args, catch_exceptions=False, **kwargs)


def run_packit(*args, working_dir=None, **kwargs):
    working_dir = working_dir or Path.cwd()
    with cwd(working_dir):
        cli_runner = CliRunner()
        cli_runner.invoke(packit_base, *args, catch_exceptions=False, **kwargs)
