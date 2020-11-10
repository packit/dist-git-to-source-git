# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import os
import re
import shutil
from logging import getLogger
from pathlib import Path
import git

from ogr import PagureService
from dist2src.core import Dist2Src
from dist2src.worker.monitoring import Pushgateway
from dist2src.worker.logging import set_logging_to_file

logger = getLogger(__name__)


class Processor:
    def process_message(self, event: dict, **kwargs):
        workdir = Path(os.getenv("D2S_WORKDIR", "/workdir"))
        dist_git_host = os.getenv("D2S_DIST_GIT_HOST", "git.centos.org")
        src_git_host = os.getenv("D2S_SRC_GIT_HOST", "git.stg.centos.org")
        src_git_token = os.getenv("D2S_SRC_GIT_TOKEN")
        dist_git_namespace = os.getenv("D2S_DIST_GIT_NAMESPACE", "rpms")
        src_git_namespace = os.getenv("D2S_SRC_GIT_NAMESPACE", "source-git")
        branches_watched = os.getenv("D2S_BRANCHES_WATCHED", "c8s,c8").split(",")
        fullname = event["repo"]["fullname"]
        name = event["repo"]["name"]
        branch = event["branch"]

        logger.info(f"Processing message with {event}")
        # Is this a repository in the rpms namespace?
        if not fullname.startswith(dist_git_namespace):
            logger.info(
                f"Ignore update event for {fullname}. Not in the '{dist_git_namespace}' namespace."
            )
            Pushgateway().push_received_message(ignored=True)
            return

        # Should this branch be updated?
        if event["branch"] not in branches_watched:
            logger.info(
                f"Ignore update event for {fullname}. "
                f"Branch {event['branch']!r} is not one of the "
                f"watched branches: {branches_watched}."
            )
            Pushgateway().push_received_message(ignored=True)
            return

        # Does this repository have a source-git equvalent?
        service = PagureService(
            instance_url=f"https://{src_git_host}", token=src_git_token
        )
        # When the namespace is a fork, "fork" is singular when accessing
        # the API, but plural in the Git URLs.
        # Keep this here, so we can test with forks.
        namespace = re.sub(r"^forks\/", "fork/", src_git_namespace)
        project = service.get_project(namespace=namespace, repo=name)
        if not project.exists():
            logger.info(
                f"Ignore update event for {fullname}. "
                "The corresponding source-git repo does not exist."
            )
            Pushgateway().push_received_message(ignored=True)
            return

        Pushgateway().push_received_message(ignored=False)
        set_logging_to_file(repo_name=name, commit_sha=event["end_commit"])

        # Clone repo from rpms/ and checkout the branch.
        dist_git_dir = workdir / fullname
        shutil.rmtree(dist_git_dir, ignore_errors=True)
        dist_git_repo = git.Repo.clone_from(
            f"https://{dist_git_host}/{fullname}.git", dist_git_dir
        )
        dist_git_repo.git.checkout(branch)

        # Check if the commit is the one we are expecting.
        if dist_git_repo.branches[branch].commit.hexsha != event["end_commit"]:
            logger.warning(
                f"HEAD of {branch} is not matching {event['end_commit']}, as expected."
            )

        # Clone repo from source-git/ using ssh, so it can be pushed later on.
        src_git_ssh_url = project.get_git_urls()["ssh"]
        src_git_dir = workdir / src_git_namespace / name
        shutil.rmtree(src_git_dir, ignore_errors=True)
        src_git_repo = git.Repo.clone_from(
            src_git_ssh_url,
            src_git_dir,
        )

        # Check-out the source-git branch, if already exists,
        # so that 'convert' knows that this is an update.
        remote_heads = [
            ref.remote_head
            for ref in src_git_repo.references
            if isinstance(ref, git.RemoteReference)
        ]
        if branch in remote_heads:
            src_git_repo.git.checkout(branch)

        d2s = Dist2Src(
            dist_git_path=dist_git_dir,
            source_git_path=src_git_dir,
        )
        d2s.convert(branch, branch)

        # Push the result to source-git.

        # Update moves sg-start tag, we need --tags --force to move it in remote.
        src_git_repo.git.push("origin", branch, tags=True, force=True)
        Pushgateway().push_created_update()
