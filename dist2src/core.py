#!/usr/bin/python3

# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
import logging
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Union, Set, Dict

import git
import requests
import sh
from git import GitCommandError
from packit.config import get_local_package_config
from packit.patches import PatchMetadata
from packit.specfile import Specfile
import yaml

from dist2src.constants import (
    AFTER_PREP_HOOK,
    TEMP_SG_BRANCH,
    START_TAG_TEMPLATE,
    TARGETS,
    HOOKS,
    VERY_VERY_HARD_PACKAGES,
)

logger = logging.getLogger(__name__)


# https://stackoverflow.com/questions/13518819/avoid-references-in-pyyaml
# mypy hated the suggestion from the SA ^, hence an override like this
class SafeDumperWithoutAliases(yaml.SafeDumper):
    def ignore_aliases(self, data):
        # no aliases/anchors in the dumped yaml text
        return True


def get_hook(package_name: str, hook_name: str) -> Optional[str]:
    """get a hook's command for particular source-git repo"""
    return HOOKS.get(package_name, {}).get(hook_name, None)


def get_build_dir(path: Path) -> Path:
    build_dirs = [d for d in (path / "BUILD").iterdir() if d.is_dir()]
    if len(build_dirs) > 1:
        raise RuntimeError(f"More than one directory found in {path / 'BUILD'}")
    if len(build_dirs) < 1:
        raise RuntimeError(f"No subdirectory found in {path / 'BUILD'}")
    return build_dirs[0]


class GitRepo:
    """
    a wrapper on top of git.Repo for our convenience
    """

    def __init__(self, repo_path: Optional[Path], create: bool = False):
        self.repo_path = repo_path
        # some CLI commands don't pass both paths,
        # let's just set it to None and move on
        if not repo_path:
            self.repo = None
        elif create:
            repo_path.mkdir(parents=True, exist_ok=True)
            self.repo = git.Repo.init(repo_path)
        else:
            self.repo = git.Repo(repo_path)

    def __str__(self):
        ref = None
        if self.repo:
            ref = self.repo.active_branch
        return f"GitRepo(path={self.repo_path}, ref={ref})"

    def has_ref(self, ref: str):
        """
        does this repo have a ref?

        @param ref: the ref to check via repo.branches and remote[].refs
        @return: bool
        """
        if ref in self.repo.branches:
            return True
        # .branches does not contain all remote refs = branches
        # (Pdb) self.source_git.repo.branches
        # [<git.Head "refs/heads/master">]
        # (Pdb) self.source_git.repo.remotes["origin"].refs
        # [<git.RemoteReference "refs/remotes/origin/HEAD">,
        #  <git.RemoteReference "refs/remotes/origin/c8">,
        #  <git.RemoteReference "refs/remotes/origin/master">]
        if "origin" in self.repo.remotes:
            return ref in self.repo.remotes["origin"].refs
        return False

    def checkout(self, branch: str, orphan: bool = False, create_branch: bool = False):
        """
        Run `git checkout` in the git repo.

        @param branch: name of the branch to check out
        @param orphan: Create a branch with disconnected history.
        @param create_branch: Create branch if it doesn't exist (using -B)
        """
        if orphan:
            self.repo.git.checkout("--orphan", branch)
            # when creating an orphan branch, git preserves files in the index
            # we don't want those, hush!
            if self.repo.index.entries:
                for entry in self.repo.index.entries:
                    # entry = (path, stage number) -- see BaseIndexEntry.stage
                    self.repo.index.remove(entry[0], working_tree=True, r=True, f=True)
        elif create_branch:
            self.repo.git.checkout("-B", branch)
        else:
            self.repo.git.checkout(branch, force=True)

    def commit(self, message: str, body: Optional[str] = None):
        """Commit staged changes in GITDIR."""
        other_message_kwargs = {"message": body} if body else {}
        # some of the commits may be empty and it's not an error,
        # e.g. extra source files
        self.repo.git.commit(allow_empty=True, m=message, **other_message_kwargs)

    def commit_all(self, message: str):
        if self.repo.is_dirty():
            self.stage()
            self.commit(message=message)
        else:
            logger.info("The repo is not dirty, nothing to commit.")

    def fetch(self, remote: Union[str, Path], refspec: str):
        """
        fetch refs from a remote to this repo

        @param remote: str or path of the repo we fetch from
        @param refspec: see man git-fetch
        """
        self.repo.git.fetch(remote, refspec)

    def stage(self, add=None, rm=None, exclude=None):
        """stage content in the repo (git add)"""
        if exclude:
            exclude = f":(exclude){exclude}"
            logger.debug(exclude)
        if rm:
            self.repo.git.rm(rm, "-f", exclude)
        else:
            self.repo.git.add(add or ".", "-f", exclude)

    def create_tag(self, tag, branch):
        """Create a Git TAG at the tip of BRANCH"""
        self.repo.create_tag(tag, ref=branch, force=True)

    def get_tags_for_head(self) -> List[str]:
        return list(
            tag.name for tag in self.repo.tags if tag.commit == self.repo.head.commit
        )

    def cherry_pick_base(self, from_branch, to_branch, theirs=False):
        """Cherry-pick the first commit of a branch

        Cherry-pick the first commit of FROM_BRANCH to TO_BRANCH in the
        repository stored in GITDIR.
        """
        num_commits = sum(1 for _ in self.repo.iter_commits(from_branch))
        self.checkout(to_branch, create_branch=True)
        git_options = (
            {
                "strategy": "recursive",
                "strategy_option": "theirs",
                "keep_redundant_commits": True,
            }
            if theirs
            else {}
        )
        if self.repo.is_dirty():
            raise RuntimeError(
                "We wanted to cherry-pick the base commit but the source-git repo "
                "is dirty when it shouldn't be."
            )
        try:
            self.repo.git.cherry_pick(f"{from_branch}~{num_commits - 1}", **git_options)
        except GitCommandError as ex:
            if "nothing to commit" in str(ex):
                self.commit(message="Base commit: empty - no source archive")
            elif "could not apply" in str(ex):
                # even though we are doing -Xtheirs, git still can fail resolving conflicts
                # which is really weird; in such a case, let's just `add .` and continue
                # the cherry-pick process
                self.repo.git.checkout("--theirs", ".")
                self.stage(".")
                # cherry-pick prompts an editor here
                self.repo.git.cherry_pick("--continue")
                if self.repo.is_dirty():
                    raise RuntimeError(
                        "We wanted to cherry-pick the base commit but the source-git repo "
                        "is dirty when it shouldn't be."
                    )
            else:
                raise

    def revert_to_ref(
        self,
        ref,
        commit_message: Optional[str] = None,
        commit_body: Optional[str] = None,
    ):
        commit_message = commit_message or f"Revert the state to {ref}"
        # https://git-scm.com/book/en/v2/Git-Tools-Reset-Demystified
        # Reset index without changing HEAD
        self.repo.git.reset(ref, ".")
        self.commit(commit_message, body=commit_body)
        # clear the working-tree
        self.repo.git.reset("HEAD", hard=True)
        self.clean()  # `reset --hard HEAD` is not enough to clean untracked files
        # EOL normalization can still leave the repo in a dirty state.
        # Make sure these changes are part of the revert commit.
        if self.repo.is_dirty():
            self.repo.git.add("--renormalize", ".")
            self.repo.git.commit("--amend", "--no-edit")

    def clean(self):
        """
        Clean the repo.
        """
        # We need to use two `force` options
        # to remove the submodules/git repos as well.
        self.repo.git.clean("-xdff")

    def fast_forward(self, branch, to_ref):
        self.checkout(branch)
        self.repo.git.merge(to_ref, ff_only=True)

    @property
    def packit_upstream_ref(self):
        """
        Get the 'upstream_ref' value from Packit configuration.
        """
        package_config = get_local_package_config(self.repo.working_dir)
        return package_config.upstream_ref

    def is_file_tracked(self, path: str) -> bool:
        try:
            self.repo.git.ls_files("--error-unmatch", path)
        except GitCommandError:
            return False
        return True


class Dist2Src:
    """
    A convertor for dist-git rpm repos into a source-git variant.
    """

    def __init__(
        self,
        dist_git_path: Optional[Path],
        source_git_path: Optional[Path],
        log_level: int = 1,
    ):
        """
        both dist_git_path and source_git_path are optional because not all operations require both

        @param dist_git_path: path to the dist-git repo we want to convert
        @param source_git_path: path to a source-git repo (doesn't need to exist)
                                where the conversion output will land
        @param log_level: int, 0 minimal output, 1 verbose, 2 debug
        """
        # we are using absolute paths since we do pushd below before running rpmbuild
        # and in that case relative paths no longer work
        self.dist_git_path = dist_git_path.absolute() if dist_git_path else None
        self.dist_git = GitRepo(self.dist_git_path)
        self.source_git_path = source_git_path.absolute() if source_git_path else None
        self.source_git = GitRepo(self.source_git_path, create=True)
        self.log_level = log_level
        self._dist_git_spec = None

    @property
    def dist_git_spec(self):
        if self._dist_git_spec:
            return self._dist_git_spec
        if not self.dist_git_path:
            raise RuntimeError("dist_git_path not defined")
        self._dist_git_spec = Specfile(
            self.dist_git_path / self.relative_specfile_path,
            sources_dir=self.dist_git_path / "SOURCES/",
        )
        return self._dist_git_spec

    # This method would run only once during the lifetime of the Dist2Src object and
    # return the cached return value for subsequent calls to save compute
    # since the file will not change.
    @lru_cache()
    def lookaside_sources(self) -> Dict[str, str]:
        """
        read .{package_name}.metadata and return a `Dict[path: sha]`
        with hash of the source and the target path

        @return: {path1: sha1, path2: sha3}
        """
        metadata_file_content = next(self.dist_git_path.glob(".*.metadata")).read_text()
        source_lines = metadata_file_content.strip().split("\n")
        sources: Dict[str, str] = {}
        for source_line in source_lines:
            if not source_line:
                # the metadata file can actually be empty for packages which don't have sources
                #   e.g. hyperv-daemons, python-rpm-generators
                continue
            sha, path = source_line.split(" ")
            sources[path] = sha
        # making sure the dict is unique and methods can't mutate it b/w each other
        return sources.copy()

    @property
    def BUILD_repo_path(self) -> Path:
        """
        return path to the git repo generated after running rpmbuild -bp
        it resides in dist-git/BUILD/NAME-VERSION/
        """
        # Make it absolute, so that it's easier to use it with 'fetch'
        # running from dest_dir
        return get_build_dir(self.dist_git_path).absolute()

    @property
    def package_name(self):
        if self.dist_git_path:
            return self.dist_git_path.name
        elif self.source_git_path:
            return self.source_git_path.name
        raise RuntimeError(
            "I'm sorry but nor dist_git_path nor source_git_path are defined."
        )

    @property
    def relative_specfile_path(self):
        return f"SPECS/{self.package_name}.spec"

    def fetch_archive(
        self,
        get_sources_script_path: str = os.getenv(
            "DIST2SRC_GET_SOURCES", "get_sources.sh"
        ),
    ):
        """
        Fetch archive using get_sources.sh script in the dist-git repo.
        """
        command = sh.Command(get_sources_script_path)

        with sh.pushd(self.dist_git_path):
            logger.info(f"Running command {get_sources_script_path} in {os.getcwd()}")
            stdout = command()

        logger.debug(f"output = {stdout}")

    def _enforce_autosetup(self):
        """
        We are unable to get a git repo when a packages uses %setup + %patch
        so we need to turn %setup into %autosetup -N

        this method makes sure there is a git repo in <REPO>/PACKAGE-VERSION/.git
        after running %prep, this is how:
        1. %autosetup - cool: just "return"
        2. %autopatch - it calls to %__scm_apply_%{...} which we override: just "return"
        3. %setup and no %patch - we need to turn %setup into %autosetup to create
           the git repo
        4. %setup + %patch - most common and complicated as hell:
           a) %setup -a -a ... - we can't turn it to %autosetup b/c
              `%autosetup -a -a` doesn't work https://bugzilla.redhat.com/show_bug.cgi?id=1881840
           b) %setup + pushd/cd - we cannot recreate those patches correctly since
              they are not applied from root #92
           c) %setup -T - do not unpack SOURCE0: in this case we don't want %autosetup b/c
              it would be empty, we need to rely on %patch
           d) no bullshit, just plain %setup and %patch -- in any case, we turn
              %setup into %autosetup -N to be sure the .git repo is created correctly
              unless `-a -a` is used
        """
        prep_lines = self.dist_git_spec.spec_content.section("%prep")

        if not prep_lines:
            # e.g. appstream-data does not have a %prep section
            return

        a_a_regex = re.compile(r"-a")
        # -T means to not unpack, it can actually be set e.g. like "-cT"
        cap_t_regex = re.compile(r"-[a-zA-Z]*T")
        for i, line in enumerate(prep_lines):
            if line.startswith(("%autosetup", "%autopatch")):
                logger.info("This package uses %autosetup or %autopatch.")
                # cool, we're good
                return
            elif line.startswith("%setup"):
                if len(a_a_regex.findall(line)) >= 2:
                    logger.info(
                        "`%setup -aN -aM` detected, we cannot turn it to %autosetup"
                    )
                    continue
                if cap_t_regex.findall(line):
                    logger.info(
                        "`%setup -T` detected - no %autosetup, we need to rely on %patch"
                    )
                    continue
                # %setup -> %autosetup -N
                prep_lines[i] = line.replace("%setup", "%autosetup -N")
                # %autosetup does not accept -q, remove it
                prep_lines[i] = re.sub(r"\s+-q", r"", prep_lines[i])

            if prep_lines[i] != line:
                logger.debug(f"{line!r} -> {prep_lines[i]!r}")

        self.dist_git_spec.save()

    def run_prep(self, ensure_autosetup: bool = True):
        """
        run `rpmbuild -bp` in the dist-git repo to get a git-repo
        in the %prep phase so we can pick the commits in the source-git repo

        @param ensure_autosetup: replace %setup with %autosetup if possible
        """
        rpmbuild = sh.Command("rpmbuild")

        with sh.pushd(self.dist_git_path):
            BUILD_dir = Path("BUILD")
            if BUILD_dir.is_dir():
                # remove BUILD/ dir if it exists
                # for single-commit repos, this is problem in case of a rebase
                # there would be 2 directories which the get_build_dir() function
                # would not handle
                shutil.rmtree(BUILD_dir)

            cwd = Path.cwd()
            logger.debug(f"Running rpmbuild in {cwd}")
            specfile_path = Path(f"SPECS/{cwd.name}.spec")

            rpmbuild_args = [
                "--nodeps",
                "--define",
                f"_topdir {cwd}",
                "-bp",
            ]
            if self.log_level:  # -vv can be super-duper verbose
                rpmbuild_args.append("-" + "v" * self.log_level)
            rpmbuild_args.append(str(specfile_path))

            if ensure_autosetup:
                self._enforce_autosetup()

            try:
                running_cmd = rpmbuild(*rpmbuild_args)
            except sh.ErrorReturnCode as e:
                # This might create a tons of error logs.
                # Create a child logger, so that it's possible to filter
                # for them, for example in Sentry.
                rpmbuild_logger = logger.getChild("rpmbuild")
                for line in e.stderr.splitlines():
                    rpmbuild_logger.error(str(line))
                # Also log the failure using the main logger.
                logger.error(f"{['rpmbuild', *rpmbuild_args]} failed")
                raise

            self.dist_git.repo.git.checkout(self.relative_specfile_path)

            logger.debug(f"rpmbuild stdout = {running_cmd}")  # this will print stdout
            logger.info(f"rpmbuild stderr = {running_cmd.stderr.decode()}")

            hook_cmd = get_hook(self.package_name, AFTER_PREP_HOOK)
            if hook_cmd:
                bash = sh.Command("bash")
                bash("-c", hook_cmd)

    def fetch_branch(self, source_branch: str, dest_branch: str):
        """Fetch the branch produced by 'rpmbuild -bp' from the dist-git
        repo to the source-git repo.

        @param source_branch: branch from which we fetch
        @param dest_branch: branch to which the history should be fetched.
        """
        logger.info(
            f"Fetch the dist-git %prep branch to source-git branch {dest_branch}."
        )
        self.source_git.fetch(self.BUILD_repo_path, f"+{source_branch}:{dest_branch}")

    def remove_gitlab_ci_config(self):
        """remove config files for gitlab CI so it's not being triggered"""
        # luckily it's only a single file:
        #   https://docs.gitlab.com/ee/ci/quick_start/#create-a-gitlab-ciyml-file
        gitlab_config_name = ".gitlab-ci.yml"
        gitlab_ci_path = self.source_git_path / gitlab_config_name
        if gitlab_ci_path.is_file():
            gitlab_ci_path.unlink()
            try:
                self.source_git.stage(rm=gitlab_config_name)
            except GitCommandError as ex:
                # e.g. kernel
                logger.info(
                    f"It seems that {gitlab_config_name} is not tracked by git: {ex}"
                )
            else:
                self.source_git.commit(
                    message="Remove GitLab CI config file\n\nignore: true"
                )

    def perform_convert(
        self, origin_branch: str, dest_branch: str, source_git_tag: str
    ):
        """Run all the steps to get a source-git repo from dist-git"""
        self.dist_git.checkout(branch=origin_branch)
        if self.source_git.repo.active_branch.name != dest_branch:
            if self.source_git.has_ref(dest_branch):
                update = True
                self.source_git.checkout(branch=dest_branch)
            else:
                update = False
                self.source_git.checkout(branch=dest_branch, orphan=True)
        else:
            update = True

        # expand dist-git and pull the history
        self.fetch_archive()
        self.run_prep()
        if not (self.BUILD_repo_path / ".git").is_dir():
            raise RuntimeError(
                ".git repo not present in the BUILD/ dir after running %prep"
            )
        BUILD_repo = GitRepo(self.BUILD_repo_path)
        # since this is not a patch, we want packit to ignore it
        BUILD_repo.commit_all(message="Changes after running %prep\n\nignore: true")
        self.fetch_branch(source_branch="master", dest_branch=TEMP_SG_BRANCH)
        self.source_git.cherry_pick_base(
            from_branch=TEMP_SG_BRANCH, to_branch=dest_branch, theirs=update
        )

        # configure packit
        self.add_packit_config(
            upstream_ref=source_git_tag,
            lookaside_branch=origin_branch,
            commit=True,
        )
        self.copy_spec()
        self.source_git.stage(add="SPECS")
        self.source_git.commit(message="Add spec-file for the distribution")

        self.remove_gitlab_ci_config()

        self.copy_all_sources()
        self.copy_conditional_patches()
        self.source_git.stage(add="SPECS")
        self.source_git.commit(message="Add sources defined in the spec file")

        # mark the last upstream commit
        self.source_git.create_tag(tag=source_git_tag, branch=dest_branch)

        # get all the patch-commits
        self.rebase_patches(from_branch=TEMP_SG_BRANCH, to_branch=dest_branch)

    def convert(self, origin_branch: str, dest_branch: str):
        """
        Convert a dist-git repository into a source-git repo.
        Update the source-git repo if it exists.

        This is the entrypoint method.
        """
        if self.package_name in VERY_VERY_HARD_PACKAGES:
            self.convert_single_commit(origin_branch, dest_branch)
        elif self.source_git_path.exists() and self.source_git.has_ref(dest_branch):
            logger.info(
                "The source-git repository and branch exist. Updating existing source-git..."
            )
            self.update_source_git(origin_branch, dest_branch)
        else:
            self.perform_convert(
                origin_branch,
                dest_branch,
                START_TAG_TEMPLATE.format(branch=dest_branch),
            )

    def move_prep_content(self):
        """
        For the single-commit source-git repos, we don't care about the
        git repo created in BUILD/<PACKAGE-VERSION> since it's wrong
        hence we only move the content to the source-git repo and commit it
        """
        for entry in self.BUILD_repo_path.iterdir():
            if entry.name != ".git":
                logger.debug(f"move {entry} -> {self.source_git_path}")
                # 'move' has issues with Path objects in older Python
                # https://github.com/python/cpython/pull/15326
                shutil.move(str(entry), str(self.source_git_path))

    def convert_single_commit(self, origin_branch: str, dest_branch: str):
        """
        Convert a dist-git repository into a source-git repo in a single
        source-git commit - we use this strategy for packages with complex
        %prep sections (multiple archives, patching subdir, redefining %scm* macros....)
        which cannot be converted well with the convert() function
        """
        logger.info(
            "Doing a single-commit source-git repo "
            f"for {self.package_name}:{origin_branch}"
        )
        self.dist_git.checkout(branch=origin_branch)
        if self.source_git.repo.active_branch.name != dest_branch:
            self.source_git.checkout(branch=dest_branch, orphan=True)

        # if it's an update, we need to remove everything except for .git
        for path in self.source_git_path.iterdir():
            if path.name == ".git":
                continue
            logger.debug(f"rm {path}")
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

        # expand dist-git and pull the history
        self.fetch_archive()
        self.run_prep(ensure_autosetup=False)
        self.move_prep_content()

        # configure packit
        source_git_tag = START_TAG_TEMPLATE.format(branch=dest_branch)
        self.add_packit_config(
            upstream_ref=source_git_tag,
            lookaside_branch=origin_branch,
            commit=False,
        )
        self.copy_spec()
        self.remove_gitlab_ci_config()
        self.copy_all_sources(with_patches=True)
        self.source_git.stage(add=".")

        try:
            commit_msg_suffix = (
                subprocess.check_output(
                    ["git", "describe", "--abbrev=0"], cwd=self.dist_git_path
                )
                .decode()
                .strip()
            )
        except subprocess.CalledProcessError:
            logger.error("couldn't obtain latest git-tag from the dist-git repo")
            commit_msg_suffix = self.package_name
        self.source_git.commit(message=f"Source-git repo for {commit_msg_suffix}")

        # mark the last upstream commit
        self.source_git.create_tag(tag=source_git_tag, branch=dest_branch)

    def get_lookaside_sources(self, branch: str) -> List[Dict[str, str]]:
        """
        Return "sources" which are meant to be set in packit.yaml so that
        packit can fetch them from the lookaside
        cache instead of committing them to source-git

        @param branch: pick up a lookaside sources from this branch (e.g. c8 or c8s)
        """
        sources: List[Dict[str, str]] = []
        for path, sha in self.lookaside_sources().items():
            url = f"https://git.centos.org/sources/{self.package_name}/{branch}/{sha}"
            response = requests.head(url)
            if response.status_code == 404:
                # so it's c8 then
                # ltrace, wireshark and more have this problem
                url = f"https://git.centos.org/sources/{self.package_name}/c8/{sha}"
                response = requests.head(url)
            if not response.ok:
                raise RuntimeError(
                    f"Source {url} does not exist - we can't locate the proper branch."
                )
            logger.debug(f"add source {url} -> {path!r}")
            # packit is too smart, it already expects the archive to be in SPECS
            # so we just strip the leading SOURCES dir
            path = path.replace("SOURCES/", "")
            sources.append({"url": url, "path": path})
        return sources

    def add_packit_config(
        self, upstream_ref: str, lookaside_branch: str, commit: bool = False
    ):
        """
        Add packit config to the source-git repo.

        @param upstream_ref: source-git history starts from this git-ref
        @param lookaside_branch: pick up a lookaside sources from this branch (e.g. c8 or c8s)
        @param commit: if True, commit the file
        """
        logger.info("Placing .packit.yaml to the source-git repo and committing it.")
        config = {
            # e.g. qemu-kvm ships "some" spec file in their tarball
            # packit doesn't need to look for the spec when we know where it is
            "specfile_path": self.relative_specfile_path,
            "upstream_ref": upstream_ref,
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
            "sources": self.get_lookaside_sources(lookaside_branch),
        }

        self.source_git_path.joinpath(".packit.yaml").write_text(
            yaml.dump_all(
                [config],
                Dumper=SafeDumperWithoutAliases,
                # default_flow_style=False dumps things into a block instead of ugly inline
                # inline example:
                #   key: {key1: value1, key2: value2}
                # block example:
                #   key:
                #     key1: value1
                #     key2: value1
                # True in el8, False in the latest pyyaml
                default_flow_style=False,
            )
        )
        if commit:
            self.source_git.stage(add=".packit.yaml")
            self.source_git.commit(message=".packit.yaml")

    def copy_all_sources(self, with_patches: bool = False):
        """
        Copy 'SOURCES/*' from a dist-git repo to a source-git repo.

        @param with_patches: copy patch files as well
        """
        dg_path = self.dist_git_path / "SOURCES"
        sg_path = self.source_git_path / "SPECS"
        logger.info(f"Copy all sources from {dg_path} to {sg_path}.")

        sources: List[str] = self.dist_git_spec.get_sources()[:]
        lookaside_source_paths = self.lookaside_sources().keys()
        if with_patches:
            sources += (x.path for x in self.dist_git_spec.get_patches())

        for source in sources:
            # sources are absolute paths as str, lookaside_paths are relative within the repo
            relative = Path(source).relative_to(self.dist_git_path)
            if str(relative) in lookaside_source_paths:
                if self.dist_git.is_file_tracked(str(relative)):
                    raise RuntimeError(
                        f"File {relative} is stored in the lookaside cache and in git"
                        ", which one should we use?"
                    )
                logger.debug(
                    f"Source {source} will be fetched from lookaside cache, skipping."
                )
                continue
            source_dest = sg_path / Path(source).name
            logger.debug(f"copying {source} to {source_dest}")
            shutil.copy2(source, source_dest)

    def copy_conditional_patches(self):
        """
        for patches which are applied in conditions
        and the condition is evaluated to false during conversion,
        we cannot create a SRPM because rpmbuild wants the patch files present
        and obviously packit doesn't know how to create those

        this method copies all patch files which are defined and are not in the patch metadata
        """
        patch_files_in_commits: Set[str] = set()

        BUILD_git = git.Repo(self.BUILD_repo_path)
        for commit in BUILD_git.iter_commits():
            p = PatchMetadata.from_commit(commit, None)
            if p.present_in_specfile:  # base commit doesn't have any metadata
                patch_files_in_commits.add(p.name)

        all_defined_patches = set(
            x.get_patch_name() for x in self.dist_git_spec.get_patches()
        )

        for patch_name in all_defined_patches - patch_files_in_commits:
            file_src = self.dist_git_path / "SOURCES" / patch_name
            file_dest = self.source_git_path / "SPECS" / patch_name
            logger.debug(f"copying {file_src} to {file_dest}")
            shutil.copy2(file_src, file_dest)

    def copy_spec(self):
        """
        Copy spec file from the dist-git repo to the source-git repo.
        """
        dg_spec = self.dist_git_path / self.relative_specfile_path
        sg_spec = self.source_git_path / self.relative_specfile_path
        # at this point SPECS/ does not exist, so we need to create it
        sg_spec.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Copy spec file from {dg_spec} to {sg_spec}.")
        shutil.copy2(
            dg_spec,
            sg_spec,
        )

    def rebase_patches(self, from_branch, to_branch):
        """Rebase FROM_BRANCH to TO_BRANCH

        With this commits corresponding to patches can be transferred to
        the TO_BRANCH.

        FROM_BRANCH is cleaned up (deleted).
        """
        logger.info(f"Rebase patches from {from_branch} onto {to_branch}.")

        self.source_git.checkout(to_branch)
        commits_to_cherry_pick = [
            c.hexsha[:8]  # shorter format for better readability in case of an error
            for c in self.source_git.repo.iter_commits(from_branch)
        ][-2::-1]
        if commits_to_cherry_pick:
            self.source_git.repo.git.cherry_pick(
                *commits_to_cherry_pick,
                keep_redundant_commits=True,
                allow_empty=True,
                strategy_option="theirs",
            )
        self.source_git.repo.git.branch("-D", from_branch)

    def update_source_git(self, origin_branch: str, dest_branch: str):
        """
        Update the existing source-git.

        1. Revert the patches.
        2. Convert the dist-git to source-git
        3. Fast-forward the branch

        :param origin_branch: branch used as a dist-git source
        :param dest_branch: source-git branch we need to update
        """
        self.dist_git.clean()
        self.dist_git.checkout(branch=origin_branch)

        dg_tags_for_head = self.dist_git.get_tags_for_head()
        new_dest_branch = (
            dg_tags_for_head[0]
            if dg_tags_for_head
            else f"{dest_branch}-{self.dist_git.repo.head.commit.hexsha:.8}"
        )
        self.source_git.checkout(dest_branch)
        self.source_git.checkout(branch=new_dest_branch, create_branch=True)
        self.source_git.revert_to_ref(
            self.source_git.packit_upstream_ref,
            commit_message="Prepare for a new update",
            commit_body="Reverting patches so we can apply the latest update\n"
            "and changes can be seen in the spec file and sources.",
        )
        self.perform_convert(
            origin_branch=origin_branch,
            dest_branch=new_dest_branch,
            source_git_tag=START_TAG_TEMPLATE.format(branch=dest_branch),
        )

        # fast-forward old branch
        self.source_git.fast_forward(branch=dest_branch, to_ref=new_dest_branch)
