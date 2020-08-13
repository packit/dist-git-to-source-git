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
from typing import Optional, List, Dict, Any

import click
import git
import sh
import timeout_decorator
from packit.config.package_config import get_local_specfile_path
from rebasehelper.specfile import SpecFile
from yaml import dump

# packitos currently requires python>=3.7, but CentOS 8 has python==3.6 by default.
# Remove this once a version of packitos>0.13.1 is released.
try:
    from packit.patches import PatchMetadata
except ImportError:
    pass

logger = logging.getLogger(__name__)

# build/test
TARGETS = ["centos-stream-x86_64"]
START_TAG = "sg-start"

VERBOSE_KEY = "VERBOSE"

POST_CLONE_HOOK = "post-clone"
AFTER_PREP_HOOK = "after-prep"
INCLUDE_SOURCES = "include-files"

# would be better to have them externally (in a file at least)
# but since this is only for kernel, it should be good enough
KERNEL_DEBRAND_PATCH_MESSAGE = """\
Debranding CPU patch

present_in_specfile: true
location_in_specfile: 1000
patch_name: debrand-single-cpu.patch
"""
HOOKS: Dict[str, Dict[str, Any]] = {
    "kernel": {
        # %setup -c creates another directory level but patches don't expect it
        AFTER_PREP_HOOK: (
            "set -e; "
            "shopt -s dotglob nullglob && "  # so that * would match dotfiles as well
            "cd BUILD/kernel-4.18.0-*.el8/ && "
            "mv ./linux-4.18.0-*.el8.x86_64/* . && "
            "rmdir ./linux-4.18.0-*.el8.x86_64 && "
            "git add . && "
            "git commit --amend --no-edit"
            # the patch is already applied in %prep
            # "git apply ../../SOURCES/debrand-single-cpu.patch &&"
            # f"git commit -a -m '{KERNEL_DEBRAND_PATCH_MESSAGE}'"
        )
    },
    "pacemaker": {INCLUDE_SOURCES: ["nagios-agents-metadata-*.tar.gz"]},
}


def get_hook(source_git_path: Path, hook_name: str) -> Optional[str]:
    """ get a hook's command for particular source-git repo """
    package_name = source_git_path.name
    return HOOKS.get(package_name, {}).get(hook_name, None)


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
    logger.addHandler(logging.StreamHandler())
    if verbose > 1:
        logger.setLevel(logging.DEBUG)
    elif verbose > 0:
        logger.setLevel(logging.INFO)


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
@click.argument("path", type=click.Path(file_okay=False))
@click.argument("branch", type=click.STRING)
@click.option(
    "--orphan", is_flag=True, help="Create an branch with disconnected history."
)
@log_call
def checkout(path, branch, orphan=False):
    """Checkout a Git repository.

    This will create the directory at PATH, if it doesn't exist already,
    and initialize it as a Git repository. The later is not destructive
    in an existing directory.

    Checking out BRANCH is done with the `-B` flag, which means the
    branch is created if it doesn't exist or reset, if it does.
    """
    Path(path).mkdir(parents=True, exist_ok=True)

    repo = git.Repo.init(path)
    options = {}
    if orphan:
        options["orphan"] = branch

    if options:
        repo.git.checkout(**options)
    else:
        repo.git.checkout(branch)


@cli.command()
@click.argument("gitdir", type=click.Path(exists=True, file_okay=False))
@log_call
def get_archive(gitdir):
    """Calls get_sources.sh in GITDIR.

    GITDIR needs to be a dist-git repository.

    Set DIST2SRC_GET_SOURCES to the path to git_sources.sh, if it's not
    in the PATH.
    """
    script = os.getenv("DIST2SRC_GET_SOURCES", "get_sources.sh")
    command = sh.Command(script)

    with sh.pushd(gitdir):
        logger.debug(f"Running command in {os.getcwd()}")
        stdout = command()

    return stdout


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
def run_prep(ctx, path):
    """Run `rpmbuild -bp` in GITDIR.

    PATH needs to be a dist-git repository.
    """
    rpmbuild = sh.Command("rpmbuild")

    with sh.pushd(path):
        cwd = Path.cwd()
        logger.debug(f"Running rpmbuild in {cwd}")
        specfile_path = Path(f"SPECS/{cwd.name}.spec")

        verbosity_level = ""
        if ctx.obj[VERBOSE_KEY]:  # -vv can be super-duper verbose
            verbosity_level = "-" + "v" * ctx.obj[VERBOSE_KEY]
        try:
            running_cmd = rpmbuild(
                "--nodeps",
                verbosity_level,
                "--define",
                f"_topdir {cwd}",
                "-bp",
                specfile_path,
            )
        except sh.ErrorReturnCode as e:
            for line in e.stderr.splitlines():
                logger.debug(str(line))
            raise

        logger.debug(running_cmd)  # this will print stdout
        logger.debug(running_cmd.stderr.decode())

        hook_cmd = get_hook(Path(path), AFTER_PREP_HOOK)
        if hook_cmd:
            bash = sh.Command("bash")
            bash("-c", hook_cmd)

    return running_cmd.stdout  # why do we return here?


def get_build_dir(path: Path):
    build_dirs = [d for d in (path / "BUILD").iterdir() if d.is_dir()]
    if len(build_dirs) > 1:
        raise RuntimeError(f"More than one directory found in {path}")
    if len(build_dirs) < 1:
        raise RuntimeError(f"No subdirectory found in {path}")
    return build_dirs[0]


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@log_call
@click.pass_context
def commit_all(ctx, path):
    """Git add and commit all the changes in PATH.

    Do this, b/c some %prep sections will modify source code with scripts,
    and the current understanding is that we should capture these changes.
    """
    build_dir = get_build_dir(Path(path))
    repo = git.Repo(build_dir)
    if repo.is_dirty():
        ctx.invoke(stage, gitdir=build_dir)
        ctx.invoke(commit, m="Various changes", gitdir=build_dir)


@cli.command()
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("dest_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("dest_branch", type=click.STRING)
@log_call
def fetch_branch(source_dir, dest_dir, dest_branch):
    """Fetch the branch produced by 'rpmbuild -bp' from the dist-git
    repo to the source-git repo.

    SOURCE_DIR is a dist-git repository, in which there is a 'BUILD'
    subdirectory, having a single subdirectory, which is a Git repository
    produced by 'rpmbuild -bp'.

    DEST_DIR is an already initialized source-git repository.

    DEST_BRANCH is the branch to which the history should be fetched.
    """
    # Make it absolute, so that it's easier to use it with 'fetch'
    # running from dest_dir
    source_git_repo = get_build_dir(Path(source_dir)).absolute()

    repo = git.Repo(dest_dir)
    repo.git.fetch(source_git_repo, f"+master:{dest_branch}")


@cli.command()
@click.argument("gitdir", type=click.Path(exists=True, file_okay=False))
@click.argument("from_branch", type=click.STRING)
@click.argument("to_branch", type=click.STRING)
@log_call
def cherry_pick_base(gitdir, from_branch, to_branch):
    """Cherry-pick the first commit of a branch

    Cherry-pick the first commit of FROM_BRANCH to TO_BRANCH in the
    repository stored in GITDIR.
    """
    repo = git.Repo(gitdir)
    num_commits = sum(1 for commit in repo.iter_commits(from_branch))
    repo.git.checkout("-B", to_branch)
    repo.git.cherry_pick(f"{from_branch}~{num_commits - 1}")


@cli.command()
@click.argument("gitdir", type=click.Path(exists=True, file_okay=False))
@click.argument("from_branch", type=click.STRING)
@click.argument("to_branch", type=click.STRING)
@log_call
@click.pass_context
def rebase_patches(ctx, gitdir, from_branch, to_branch):
    """Rebase FROM_BRANCH to TO_BRANCH

    With this commits corresponding to patches can be transferred to
    the TO_BRANCH.

    FROM_BRANCH is cleaned up (deleted).
    """
    repo = git.Repo(gitdir)
    repo.git.checkout(from_branch)

    if repo.head.commit.message == "Various changes\n":
        repo.git.checkout(to_branch)
        repo.git.cherry_pick(from_branch)
        ctx.invoke(create_tag, tag=START_TAG, path=gitdir, branch=to_branch)
        repo.git.checkout(from_branch)
        repo.git.reset("--hard", "HEAD^")

    repo.git.rebase("--root", "--onto", to_branch)
    repo.git.checkout(to_branch)
    repo.git.merge("--ff-only", "-q", from_branch)
    repo.git.branch("-d", from_branch)


def _copy_files(
    origin: Path,
    dest: Path,
    glob: str,
    ignore_tarballs: bool = False,
    ignore_patches: bool = False,
    include_files: Optional[List[str]] = None,
) -> None:
    """
    Copy all glob files from origin to dest
    """
    dest.mkdir(parents=True, exist_ok=True)

    present_files = set(origin.glob(glob))
    files_to_copy = set()

    if include_files:
        for i in include_files:
            files_to_copy.update(set(origin.glob(i)))

    if ignore_tarballs:
        for e in ("*.tar.gz", "*.tar.xz", "*.tar.bz2"):
            present_files.difference_update(set(origin.glob(e)))
    if ignore_patches:
        present_files.difference_update(set(origin.glob("*.patch")))

    files_to_copy.update(present_files)

    for file_ in files_to_copy:
        file_dest = dest / file_.name
        logger.debug(f"copying {file_} to {file_dest}")
        shutil.copy2(file_, file_dest)


@cli.command()
@click.argument("origin", type=click.Path(exists=True, file_okay=False))
@click.argument("dest", type=click.Path(exists=True, file_okay=False))
@log_call
@click.pass_context
def copy_spec(ctx, origin, dest):
    """Copy 'SPECS/*.spec' from a dist-git repo to a source-git repo."""
    _copy_files(origin=Path(origin) / "SPECS", dest=Path(dest) / "SPECS", glob="*.spec")


@cli.command()
@click.argument("origin", type=click.Path(exists=True, file_okay=False))
@click.argument("dest", type=click.Path(exists=True, file_okay=False))
@log_call
@click.pass_context
def copy_all_sources(ctx, origin, dest):
    """Copy 'SOURCES/*' from a dist-git repo to a source-git repo."""
    include_files = get_hook(Path(dest), INCLUDE_SOURCES)
    _copy_files(
        origin=Path(origin) / "SOURCES",
        dest=Path(dest) / "SPECS",
        glob="*",
        ignore_tarballs=True,
        ignore_patches=True,
        include_files=include_files,
    )


@cli.command()
@click.argument("dest", type=click.Path(exists=True, file_okay=False))
@log_call
@click.pass_context
def add_packit_config(ctx, dest: Path):
    config = {
        # e.g. qemu-kvm ships "some" spec file in their tarball
        # packit doesn't need to look for the spec when we know where it is
        "specfile_path": f"SPECS/{dest.name}.spec",
        "upstream_ref": START_TAG,
        "jobs": [
            {
                "job": "copr_build",
                "trigger": "pull_request",
                "metadata": {"targets": TARGETS},
            },
            {
                "job": "tests",
                "trigger": "pull_request",
                "metadata": {"targets": TARGETS},
            },
        ],
    }
    Path(dest, ".packit.yaml").write_text(dump(config))
    ctx.invoke(stage, gitdir=dest, add=".packit.yaml")
    ctx.invoke(commit, m=".packit.yaml", gitdir=dest)


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
@click.argument("gitdir", type=click.Path(exists=True, file_okay=False))
@click.option("-m", default="Import sources from dist-git", help="Git commmit message")
@log_call
def commit(gitdir, m):
    """Commit staged changes in GITDIR."""
    repo = git.Repo(gitdir)
    # some of the commits may be empty and it's not an error, e.g. extra source files
    repo.git.commit("--allow-empty", m=m)


@cli.command()
@click.argument("gitdir", type=click.Path(exists=True, file_okay=False))
@click.option("--add", help="Files to add content from. Accepts globs (e.g. *.spec).")
@click.option("--exclude", help="Path to exclude from staging, relative to GITDIR")
@log_call
def stage(gitdir, add=None, exclude=None):
    """Stage content in GITDIR."""
    repo = git.Repo(gitdir)
    if exclude:
        exclude = f":(exclude){exclude}"
        logger.debug(exclude)
    repo.git.add(add or ".", exclude)


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


@cli.command("create-tag")
@click.argument("tag", type=click.STRING)
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@click.argument("branch", type=click.STRING)
@log_call
def create_tag(tag, path, branch):
    """Create a Git TAG at the tip of BRANCH
    """
    repo = git.Repo(path)
    repo.create_tag(tag, ref=branch, force=True)


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
def convert_with_prep(ctx, origin, dest):
    """Convert a dist-git repository into a source-git repository, using
    'rpmbuild' and executing the "%prep" stage from the spec file.

    ORIGIN and DEST are in the format of

        REPO_PATH:BRANCH

    This command calls all the other commands.
    """
    origin_dir, origin_branch = origin.split(":")
    dest_dir, dest_branch = dest.split(":")

    ctx.invoke(checkout, path=origin_dir, branch=origin_branch)
    ctx.invoke(checkout, path=dest_dir, branch=dest_branch, orphan=True)

    # expand dist-git and pull the history
    ctx.invoke(get_archive, gitdir=origin_dir)
    ctx.invoke(run_prep, path=origin_dir)
    ctx.invoke(commit_all, path=origin_dir)
    ctx.invoke(
        fetch_branch, source_dir=origin_dir, dest_dir=dest_dir, dest_branch="updates"
    )
    ctx.invoke(
        cherry_pick_base, gitdir=dest_dir, from_branch="updates", to_branch=dest_branch
    )

    # configure packit
    ctx.invoke(add_packit_config, dest=Path(dest_dir))
    ctx.invoke(copy_spec, origin=origin_dir, dest=dest_dir)
    ctx.invoke(stage, gitdir=dest_dir, add="SPECS")
    ctx.invoke(commit, m="Add spec-file for the distribution", gitdir=dest_dir)

    ctx.invoke(copy_all_sources, origin=origin_dir, dest=dest_dir)
    ctx.invoke(stage, gitdir=dest_dir, add="SPECS")
    ctx.invoke(commit, m="Add sources defined in the spec file", gitdir=dest_dir)

    # mark the last upstream commit
    ctx.invoke(create_tag, tag=START_TAG, path=dest_dir, branch=dest_branch)

    # get all the patch-commits
    ctx.invoke(
        rebase_patches, gitdir=dest_dir, from_branch="updates", to_branch=dest_branch
    )


if __name__ == "__main__":
    cli()
