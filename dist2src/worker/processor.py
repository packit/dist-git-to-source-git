# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import shutil
from logging import getLogger
from pathlib import Path
from typing import Optional

import git
from ogr.services.pagure import PagureProject

from dist2src.core import Dist2Src
from dist2src.worker.monitoring import Pushgateway
from dist2src.worker.config import Configuration
from dist2src.worker import logging as worker_logging
from dist2src.worker import singular_fork

logger = getLogger(__name__)


class Processor:
    def __init__(self):
        self.cfg = Configuration()

        self.fullname: Optional[str] = None
        self.name: Optional[str] = None
        self.branch: Optional[str] = None
        self.end_commit: Optional[str] = None
        self.dist_git_dir: Optional[Path] = None
        self.src_git_dir: Optional[Path] = None

    def process_message(self, event: dict, **kwargs):
        self.fullname = event["repo"]["fullname"]
        self.name = event["repo"]["name"]
        self.branch = event["branch"]
        self.end_commit = event["end_commit"]
        self.dist_git_dir = self.cfg.workdir / self.cfg.dist_git_namespace / self.name
        self.src_git_dir = self.cfg.workdir / self.cfg.src_git_namespace / self.name

        logger.info(f"Processing message with {event}")
        # Is this a repository in the rpms namespace?
        if not self.fullname.startswith(self.cfg.dist_git_namespace):
            logger.info(
                f"Ignore update event for {self.fullname}. "
                f"Not in the '{self.cfg.dist_git_namespace}' namespace."
            )
            Pushgateway().push_received_message(ignored=True)
            return

        # Should this branch be updated?
        if self.branch not in self.cfg.branches_watched:
            logger.info(
                f"Ignore update event for {self.fullname}. "
                f"Branch {self.branch!r} is not one of the "
                f"watched branches: {self.cfg.branches_watched}."
            )
            Pushgateway().push_received_message(ignored=True)
            return

        # Does this repository have a source-git equivalent?
        src_git_project = self.cfg.src_git_svc.get_project(
            namespace=singular_fork(self.cfg.src_git_namespace), repo=self.name
        )
        if not src_git_project.exists():
            logger.info(
                f"Ignore update event for {self.fullname}. "
                "The corresponding source-git repo does not exist."
            )
            Pushgateway().push_received_message(ignored=True)
            return

        # check if the repository is up to date
        conversion_tag = f"convert/{self.branch}/{self.end_commit}"
        if conversion_tag in src_git_project.get_tags():
            logger.info(
                f"Ignore update event for {self.fullname}. "
                "The source-git repo is already up to date."
            )
            Pushgateway().push_received_message(ignored=True)
            return

        Pushgateway().push_received_message(ignored=False)
        file_handler = worker_logging.set_logging_to_file(
            repo_name=self.name, commit_sha=self.end_commit
        )

        try:
            self.update_project(src_git_project, conversion_tag)
        finally:
            getLogger("dist2src").removeHandler(file_handler)
            self.cleanup()

    def update_project(self, project: PagureProject, conversion_tag: str):
        self.cleanup()
        # Clone repo from rpms/ and checkout the branch.
        dist_git_repo = git.Repo.clone_from(
            f"https://{self.cfg.dist_git_host}/{self.fullname}.git", self.dist_git_dir
        )
        dist_git_repo.git.checkout(self.branch)

        # Check if the commit is the one we are expecting.
        if dist_git_repo.branches[self.branch].commit.hexsha != self.end_commit:
            logger.warning(
                f"Abandon updating {self.name}. "
                f"HEAD of {self.branch!r} is not matching commit "
                f"{self.end_commit!r} for which this updated was started."
            )
            Pushgateway().push_abandoned_update()
            return

        # Clone repo from source-git/ using ssh, so it can be pushed later on.
        src_git_ssh_url = project.get_git_urls()["ssh"]
        src_git_repo = git.Repo.clone_from(
            src_git_ssh_url,
            self.src_git_dir,
        )

        # Check-out the source-git branch, if already exists,
        # so that 'convert' knows that this is an update.
        remote_heads = [
            ref.remote_head
            for ref in src_git_repo.references
            if isinstance(ref, git.RemoteReference)
        ]
        if self.branch in remote_heads:
            src_git_repo.git.checkout(self.branch)

        d2s = Dist2Src(
            dist_git_path=self.dist_git_dir,
            source_git_path=self.src_git_dir,
        )
        d2s.convert(self.branch, self.branch)

        src_git_repo.git.tag(
            "--annotate",
            "--message",
            f"Converted from commit {self.end_commit},\nfrom branch {self.branch}.",
            conversion_tag,
            src_git_repo.heads[self.branch].commit,
        )

        # Push the result to source-git.
        # Update moves the upstream ref tag, we need --tags --force to move it in remote.
        src_git_repo.git.push("origin", self.branch, tags=True, force=True)
        Pushgateway().push_created_update()

    def cleanup(self):
        if self.dist_git_dir:
            shutil.rmtree(self.dist_git_dir, ignore_errors=True)
        if self.src_git_dir:
            shutil.rmtree(self.src_git_dir, ignore_errors=True)
