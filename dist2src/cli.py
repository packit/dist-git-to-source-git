#!/usr/bin/python3

# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import functools
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

import click
import git
import timeout_decorator
from packit.config.package_config import get_local_specfile_path
from rebasehelper.specfile import SpecFile

from dist2src.core import Dist2Src

try:
    from packit.patches import PatchMetadata
except ImportError:
    pass

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


class D2SSpecFile(SpecFile):
    """ add a way to comment patches out in a spec file """

    def comment_patches(self):
        applied_patches = self.get_applied_patches()
        patch_indices = [p.index for p in applied_patches]

        pattern = re.compile(r"^Patch(?P<index>\d+)\s*:.+$")
        package = self.spec_content.section("%package")
        for i, line in enumerate(package):
            match = pattern.match(line)
            if match:
                index = int(match.group("index"))
                if index in patch_indices:
                    logger.debug(f"Commenting patch {index}")
                    package[i] = f"# {line}"
        self.spec_content.replace_section("%package", package)

        # comment out all %patch in %prep
        self._process_patches(patch_indices)
        self.save()


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


@cli.command()
@click.argument("origin", type=click.Path(exists=True, file_okay=False))
@click.argument("dest", type=click.Path(exists=True, file_okay=False))
@log_call
@click.pass_context
@timeout_decorator.timeout(300)
def extract_archive(ctx, origin, dest):
    """Extract the source archive found in ORIGIN to DEST.

    First, make sure that the archive was downloaded.

    After extracting the archive, stage and commit the changes in DEST.
    """
    # Make sure, the archive exists and use the STDOUT of get_sources.sh
    # to find out its path.
    stdout = ""
    while "exists" not in stdout:
        stdout = ctx.invoke(get_archive, gitdir=origin)
    archive = Path(origin, stdout.partition(" exists")[0])

    with tempfile.TemporaryDirectory() as tmpdir:
        shutil.unpack_archive(str(archive), tmpdir)
        # Expect an archive with a single directory.
        if len(os.listdir(tmpdir)) != 1:
            raise ValueError("Archive content is not a single directory")
        topdir = Path(tmpdir, os.listdir(tmpdir)[0])
        # These are all the files under the directory that was
        # in the archive.
        for f in topdir.iterdir():
            shutil.move(f, Path(dest, f.name))

    ctx.invoke(stage, gitdir=dest)
    ctx.invoke(commit, m="Unpack archive", gitdir=dest)


@cli.command()
@click.option(
    "--remove-patches",
    is_flag=True,
    default=False,
    help="If set, patches will be commented-out.",
)
@click.argument("gitdir", type=click.Path(exists=True, file_okay=False))
@log_call
@click.pass_context
def apply_patches(ctx, remove_patches, gitdir):
    """Apply the patches used in the SPEC-file found in GITDIR.

    Apply all the patches used in the SPEC-file, then update the
    SPEC-file by commenting the patches that were applied and deleting
    those patches from the disk.

    Stage and commit changes after each patch, except the ones in the
    'centos-packaging' directory.
    """

    specdir = Path(gitdir, "SPECS")
    specpath = specdir / get_local_specfile_path(specdir)
    logger.info(f"specpath = {specpath}")
    specfile = D2SSpecFile(specpath, sources_location=str(Path(gitdir, "SPECS")),)
    repo = git.Repo(gitdir)
    applied_patches = specfile.get_applied_patches()

    if remove_patches:
        # comment out all Patch in %package
        specfile.comment_patches()
        repo.git.add(specpath.relative_to(gitdir))
        repo.git.commit(m="Downstream spec with commented patches", allow_empty=True)

    # Create a tag marking last commit before downstream patches
    logger.info(f"Creating tag {START_TAG}")
    repo.create_tag(START_TAG)

    # Transfer all patches that were in spec into git commits ('git am' or 'git apply')
    for patch in applied_patches:
        metadata = PatchMetadata(
            name=patch.get_patch_name(),
            path=Path(patch.path),
            location_in_specfile=patch.index,
            present_in_specfile=not remove_patches,
        )

        logger.info(f"Apply {metadata.name}")
        rel_path = os.path.relpath(patch.path, gitdir)
        try:
            repo.git.am(
                metadata.path.absolute().relative_to(repo.working_dir),
                m=metadata.commit_message,
            )
        except git.exc.CommandError as e:
            logger.debug(str(e))
            repo.git.apply(rel_path, p=patch.strip)
            ctx.invoke(stage, gitdir=gitdir, exclude="SPECS")
            ctx.invoke(commit, gitdir=gitdir, m=metadata.commit_message)
        # The patch is a commit now, so clean it up.
        os.unlink(patch.path)


@cli.command()
@click.argument("origin", type=click.STRING)
@click.argument("dest", type=click.STRING)
@log_call
@click.pass_context
def convert(ctx, origin, dest):
    """Convert a dist-git repository into a source-git repository.

    ORIGIN and DEST are in the format of

        REPO_PATH:BRANCH

    This command calls all the other commands.
    """
    origin_dir, origin_branch = origin.split(":")
    dest_dir, dest_branch = dest.split(":")

    ctx.invoke(checkout, path=origin_dir, branch=origin_branch)
    ctx.invoke(checkout, path=dest_dir, branch=dest_branch, orphan=True)
    ctx.invoke(get_archive, gitdir=origin_dir)
    ctx.invoke(extract_archive, origin=origin_dir, dest=dest_dir)
    ctx.invoke(copy_spec, origin=origin_dir, dest=dest_dir)
    ctx.invoke(add_packit_config, dest=Path(dest_dir))
    ctx.invoke(copy_all_sources, origin=origin_dir, dest=dest_dir)
    ctx.invoke(apply_patches, gitdir=dest_dir)


@cli.command("comment-out-patches")
@click.argument("source-git-dir", type=click.Path(exists=True, file_okay=False))
@click.argument("absolute-sources-path", type=click.STRING)
@log_call
def comment_out_patches(source_git_dir, absolute_sources_path):
    """
    Comment out patches in the provided specfile

    source-git-dir - absolute path to the source-git repository
    specfile-path - relative path to the spec within the repo
    absolute-sources-path - path to sources ( = patches)
    """
    s = Path(source_git_dir)
    specfile_path = next(s.glob("SPECS/*.spec"))
    specfile = D2SSpecFile(str(specfile_path), sources_location=absolute_sources_path)
    if specfile.get_applied_patches():
        specfile.comment_patches()
        repo = git.Repo(source_git_dir)
        repo.git.add(specfile_path.relative_to(s))
        repo.git.commit(m="Comment out patches in spec so packit can process them")


@cli.command("convert-with-prep")
@click.argument("origin", type=click.STRING)
@click.argument("dest", type=click.STRING)
@log_call
@click.pass_context
def convert_with_prep(ctx, origin: str, dest: str):
    """Convert a dist-git repository into a source-git repository, using
    'rpmbuild' and executing the "%prep" stage from the spec file.

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
    d2s.convert(origin_branch, dest_branch)


if __name__ == "__main__":
    cli()
