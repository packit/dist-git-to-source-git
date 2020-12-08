# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import os
import re

from logging import getLogger
from typing import List, Optional, Tuple
from ogr.services.pagure import PagureProject

from dist2src.worker import singular_fork, plural_fork
from dist2src.worker.config import Configuration
from dist2src.worker.monitoring import Pushgateway

logger = getLogger(__name__)


class Updater:
    """
    Check source-git repository branches if they are up to date
    relative to their dist-git counterparts, and start a Celery task to
    update them (in case Celery is configured).
    """

    PROJECTS_PER_PAGE: int = 100

    def __init__(self, configuration: Optional[Configuration] = None):
        self.cfg = configuration or Configuration()

    def check_updates(self):
        logger.debug(f"Source-git API: {self.cfg.src_git_svc.api_url!r}")
        logger.debug(f"Source-git namespace: {self.cfg.src_git_namespace!r}")
        logger.debug(f"Dist-git API: {self.cfg.dist_git_svc.api_url!r}")
        logger.debug(f"Dist-git namespace: {self.cfg.dist_git_namespace!r}")
        logger.debug(f"Dist-git branches watched: {self.cfg.branches_watched!r}")

        m = re.match(
            r"(?P<fork>forks\/)?((?P<owner>.+)\/)?(?P<namespace>.+)",
            self.cfg.src_git_namespace,
        )

        # Get repositories in source-git
        url = f"{self.cfg.src_git_svc.api_url}projects"
        params = {
            "namespace": m["namespace"],
            "fork": m["fork"] is not None,
            "per_page": self.PROJECTS_PER_PAGE,
            "owner": m["owner"] or None,
            "short": True,
        }
        while url:
            r = self.cfg.src_git_svc.call_api(url, params=params)
            # The URL in 'next' already has the required parameters
            url, params = r["pagination"]["next"], None
            logger.debug(
                f"Next page: {url!r}. Total pages: {r['pagination']['pages']!r}."
            )
            for src_git_project in r["projects"]:
                logger.debug(f"Checking project {src_git_project['name']!r}...")
                dist_git_project = self.cfg.dist_git_svc.get_project(
                    namespace=singular_fork(self.cfg.dist_git_namespace),
                    repo=src_git_project["name"],
                )
                if not dist_git_project.exists():
                    logger.warning(
                        f"{dist_git_project.full_repo_name!r} does not exist in "
                        f"{self.cfg.dist_git_host!r}"
                    )
                    Pushgateway().push_found_missing_dist_git_repo()
                    continue

                for branch, commit in self._out_of_date_branches(
                    src_git_project["name"]
                ):
                    logger.info(
                        f"Branch {branch!r} from project "
                        f"{src_git_project['name']!r} needs to be updated."
                    )
                    self._create_task(dist_git_project, branch, commit)

    def _out_of_date_branches(self, project: str) -> List[Tuple[str, str]]:
        # Get branches with commits from their HEAD from dist-git
        url = (
            f"{self.cfg.dist_git_svc.api_url}"
            f"{singular_fork(self.cfg.dist_git_namespace)}/{project}/git/branches"
        )
        r = self.cfg.dist_git_svc.call_api(url, params={"with_commits": True})

        # Use a dict here, to save the branch corresponding to each convert-tag,
        # so that it doesn't need to be calculated again.
        expected_tags = {
            f"convert/{b}/{c}": (b, c)
            for b, c in r["branches"].items()
            if b in self.cfg.branches_watched
        }
        expected_tags_set = set(expected_tags)
        logger.debug(f"Tags expected in source-git: {expected_tags_set}")

        # Get tags from source-git
        src_git_project = self.cfg.src_git_svc.get_project(
            namespace=singular_fork(self.cfg.src_git_namespace), repo=project
        )
        src_git_tags = set(tag.name for tag in src_git_project.get_tags())
        logger.debug(f"Current tags in source-git: {src_git_tags}")
        missing_tags = expected_tags_set - src_git_tags
        logger.debug(f"Tags missing from source-git: {missing_tags}")
        return [expected_tags[tag] for tag in missing_tags]

    def _create_task(self, project: PagureProject, branch: str, commit: str):
        task_name = os.getenv("CELERY_TASK_NAME")
        if task_name is None:
            logger.debug("No task name is set, skip creating a Celery task.")
            return

        # Introduce the celery_app as a dependency only if there is a
        # Celery task name configured.
        from dist2src.worker.celerizer import celery_app

        event = {
            "repo": {
                "fullname": plural_fork(project.full_repo_name),
                "name": project.repo,
            },
            "branch": branch,
            "end_commit": commit,
        }
        logger.debug(f"Sending task {task_name!r}, with payload: {event}")
        r = celery_app.send_task(name=task_name, kwargs={"event": event})
        logger.info(f"Task UUID={r.id} sent to Celery.")
        Pushgateway().push_created_update_task()
