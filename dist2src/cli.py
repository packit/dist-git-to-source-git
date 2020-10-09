#!/usr/bin/python3

# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import functools
import logging
from pathlib import Path

import click

from dist2src.constants import VERY_VERY_HARD_PACKAGES
from dist2src.core import Dist2Src


logger = logging.getLogger(__name__)


VERBOSE_KEY = "VERBOSE"


@click.group("dist2src")
@click.option(
    "-v", "--verbose", count=True, help="Increase verbosity. Repeat to log more."
)
@click.pass_context
def cli(ctx, verbose):
    """Script to convert the tip of a branch from a dist-git repository
    into a commit on a branch in a source-git repository.

    As of now, this downloads the sources from the lookaside cache,
    unpacks them, applies all the patches, and remove the applied patches
    from the SPEC-file.

    For example to convert git.centos.org/rpms/rpm, branch 'c8s', to a
    source-git repo, with a branch also called 'c8s', in one step:

        \b
        $ cd git.centos.org
        $ dist2src convert rpms/rpm:c8s src/rpm:c8s

    For the same, but doing each conversion step separately:

        \b
        $ cd git.centos.org
        $ dist2src checkout rpms/rpm c8s
        $ dist2src checkout --orphan src/rpm c8s
        $ dist2src get-archive rpms/rpm
        $ dist2src extract-archive rpms/rpm src/rpm
        $ dist2src copy-spec rpms/rpm src/rpm
        $ dist2src add-packit-config src/rpm
        $ dist2src copy-all-sources rpms/rpm src/rpm
        $ dist2src apply-patches src/rpm
    """
    # https://click.palletsprojects.com/en/7.x/commands/#nested-handling-and-contexts
    # ensure that ctx.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    ctx.ensure_object(dict)
    ctx.obj[VERBOSE_KEY] = verbose

    global_logger = logging.getLogger(
        "dist2src"
    )  # we want to set up the logger for cli.py and core.py
    level = logging.WARNING
    if verbose > 1:
        level = logging.DEBUG
    elif verbose > 0:
        level = logging.INFO

    global_logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setLevel(level)
    global_logger.addHandler(handler)


def log_call(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        args_string = ", ".join([repr(a) for a in args])
        kwargs_string = ", ".join([f"{k}={v!r}" for k, v in kwargs.items()])
        sep = ", " if args_string and kwargs_string else ""
        logger.info(f"{func.__name__}({args_string}{sep}{kwargs_string})")
        ret = func(*args, **kwargs)
        return ret

    return wrapper


@cli.command()
@click.argument("gitdir", type=click.Path(exists=True, file_okay=False))
@log_call
@click.pass_context
def get_archive(ctx, gitdir: str):
    """Calls get_sources.sh in GITDIR.

    GITDIR needs to be a dist-git repository.

    Set DIST2SRC_GET_SOURCES to the path to git_sources.sh, if it's not
    in the PATH.
    """
    d2s = Dist2Src(
        dist_git_path=Path(gitdir), source_git_path=None, log_level=ctx.obj[VERBOSE_KEY]
    )
    d2s.fetch_archive()


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@log_call
@click.pass_context
def run_prep(ctx, path: str):
    """Run `rpmbuild -bp` in GITDIR.

    PATH needs to be a dist-git repository.
    """
    d2s = Dist2Src(
        dist_git_path=Path(path), source_git_path=None, log_level=ctx.obj[VERBOSE_KEY]
    )
    d2s.run_prep()


@cli.command()
@click.argument("gitdir", type=click.Path(exists=True, file_okay=False))
@click.argument("from_branch", type=click.STRING)
@click.argument("to_branch", type=click.STRING)
@log_call
@click.pass_context
def rebase_patches(ctx, gitdir: str, from_branch: str, to_branch: str):
    """Rebase FROM_BRANCH to TO_BRANCH

    With this commits corresponding to patches can be transferred to
    the TO_BRANCH.

    FROM_BRANCH is cleaned up (deleted).
    """
    d2s = Dist2Src(
        dist_git_path=None, source_git_path=Path(gitdir), log_level=ctx.obj[VERBOSE_KEY]
    )
    d2s.rebase_patches(from_branch, to_branch)


@cli.command()
@click.argument("origin", type=click.Path(exists=True, file_okay=False))
@click.argument("dest", type=click.Path(exists=True, file_okay=False))
@log_call
@click.pass_context
def copy_spec(ctx, origin: str, dest: str):
    """Copy 'SPECS/*.spec' from a dist-git repo to a source-git repo."""
    d2s = Dist2Src(
        dist_git_path=Path(origin),
        source_git_path=Path(dest),
        log_level=ctx.obj[VERBOSE_KEY],
    )
    d2s.copy_spec()


@cli.command()
@click.argument("origin", type=click.Path(exists=True, file_okay=False))
@click.argument("dest", type=click.Path(exists=True, file_okay=False))
@log_call
@click.pass_context
def copy_all_sources(ctx, origin: str, dest: str):
    """Copy 'SOURCES/*' from a dist-git repo to a source-git repo."""
    d2s = Dist2Src(
        dist_git_path=Path(origin),
        source_git_path=Path(dest),
        log_level=ctx.obj[VERBOSE_KEY],
    )
    d2s.copy_all_sources()


@cli.command()
@click.argument("dest", type=click.Path(exists=True, file_okay=False))
@log_call
@click.pass_context
def add_packit_config(ctx, dest: str):
    """
    Add packit config to the source-git repo and commit it.
    """
    d2s = Dist2Src(
        dist_git_path=None, source_git_path=Path(dest), log_level=ctx.obj[VERBOSE_KEY]
    )
    d2s.add_packit_config()


@cli.command("convert")
@click.argument("origin", type=click.STRING)
@click.argument("dest", type=click.STRING)
@log_call
@click.pass_context
def convert(ctx, origin: str, dest: str):
    """Convert a dist-git repository into a source-git repository, using
    'rpmbuild' and executing the "%prep" stage from the spec file.

    If the package is on the list of "hard" packages, there will be only a single
    commit representing the current dist-git tree,
    if it's not on the list, multiple commits will be in the repo:
     * upstream archive unpacked as a single commit
     * multiple commits for spec file, packit.yaml and additional sources
     * every patch is a commit

    Update if the branch exists.

    ORIGIN and DEST are in the format of

        REPO_PATH:BRANCH

    Set DIST2SRC_GET_SOURCES to the path to git_sources.sh, if it's not
    in the PATH.
    """
    origin_dir, origin_branch = origin.split(":")
    dest_dir, dest_branch = dest.split(":")
    d2s = Dist2Src(
        dist_git_path=Path(origin_dir),
        source_git_path=Path(dest_dir),
        log_level=ctx.obj[VERBOSE_KEY],
    )
    if d2s.package_name in VERY_VERY_HARD_PACKAGES:
        d2s.convert_single_commit(origin_branch, dest_branch)
    elif d2s.source_git_path.exists() and dest_branch in d2s.source_git.repo.branches:
        logger.info(
            "The source-git repository and branch exist. Updating existing source-git..."
        )
        d2s.update_source_git(origin_branch, dest_branch)
    else:
        d2s.convert(origin_branch, dest_branch)


if __name__ == "__main__":
    cli()
