# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import os
from logging import getLogger
from typing import List, Optional, Tuple

from gitlab import GitlabGetError
from gitlab.v4.objects import Group
from ogr.services.pagure import PagureProject

from dist2src.worker import sentry
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

    def check_updates(
        self, project: Optional[str] = None, branch: Optional[str] = None
    ):
        """
        Check if repositories in a source-git namespace need to be updated
        and create Celery tasks to update them, if configured and needed.

        Limit the checks to 'project' and 'branch', if the arguments are
        specified.
        """
        logger.debug(f"Source-git instance: {self.cfg.src_git_svc.instance_url!r}")
        logger.debug(f"Source-git namespace: {self.cfg.src_git_namespace!r}")
        logger.debug(f"Dist-git API: {self.cfg.dist_git_svc.api_url!r}")
        logger.debug(f"Dist-git namespace: {self.cfg.dist_git_namespace!r}")
        logger.debug(f"Dist-git branches watched: {self.cfg.branches_watched!r}")
        sentry.configure_sentry(runner_type="scheduled-update")
        if self.cfg.update_task_expires:
            logger.debug(
                f"Celery tasks created are valid for {self.cfg.update_task_expires} seconds"
            )
        else:
            logger.debug("Celery tasks created never expire")

        src_gitlab_group = self.cfg.src_git_svc.gitlab_instance.groups.get(
            self.cfg.src_git_namespace
        )

        # Check and update only 'project' if defined, otherwise
        # check and update all the projects in the namespace.
        n = 1
        if project:
            projects = [project]
        else:
            projects = self._get_project_name_in_group_for_page(src_gitlab_group, n)

        while projects:
            for project_to_be_processed in projects:
                self._check_and_update_project(project_to_be_processed, branch=branch)
            if project:
                # there is only a single project to check
                break
            n += 1
            projects = self._get_project_name_in_group_for_page(src_gitlab_group, n)

        Pushgateway().push_dist2src_finished_checking_updates()

    def _get_project_name_in_group_for_page(
        self, gitlab_group: Group, page: int
    ) -> List[str]:
        """return a list of project names in a GitLab namespace for a given page"""
        return [
            p.name
            for p in gitlab_group.projects.list(
                page=page, per_page=self.PROJECTS_PER_PAGE
            )
        ]

    def _check_and_update_project(self, project: str, branch: Optional[str] = None):
        """check selected src repo and queue update tasks for branch which are out of date"""
        dist_git_project = self._get_dist_git(project)
        if not dist_git_project.exists():
            logger.warning(
                f"{dist_git_project.full_repo_name!r} does not exist in "
                f"{self.cfg.dist_git_host!r}"
            )
            Pushgateway().push_found_missing_dist_git_repo()
            return
        for branch, commit in self._get_out_of_date_branches(project, branch):
            logger.info(
                f"Branch {branch!r} from project {project!r} needs to be updated."
            )
            self._create_task(dist_git_project, branch, commit)

    def _get_dist_git(self, project: str) -> PagureProject:
        """get corresponding dist-git repo for a src repo"""
        return self.cfg.dist_git_svc.get_project(
            namespace=singular_fork(self.cfg.dist_git_namespace),
            repo=project,
            # Specify username in order to disable superfluous whoami API calls.
            username="packit",
        )

    def _get_out_of_date_branches(
        self, project: str, branch: Optional[str] = None
    ) -> List[Tuple[str, str]]:
        """
        return a list of (branch, commit) objects for the selected source-git repo -
        the branches are out of date against their dist-git counterparts and need updating
        """
        logger.debug(f"Checking project {project!r}...")
        # Get branches with commits from their HEAD from dist-git
        url = (
            f"{self.cfg.dist_git_svc.api_url}"
            f"{singular_fork(self.cfg.dist_git_namespace)}/{project}/git/branches"
        )
        r = self.cfg.dist_git_svc.call_api(url, params={"with_commits": True})

        branch_filter = None
        if branch:
            branch_filter = lambda x: x == branch  # noqa

        # Use a dict here, to save the branch corresponding to each convert-tag,
        # so that it doesn't need to be calculated again.
        expected_tags = {
            f"convert/{b}/{c}": (b, c)
            for b, c in r["branches"].items()
            if b in filter(branch_filter, self.cfg.branches_watched)
        }
        expected_tags_set = set(expected_tags)
        logger.debug(f"Tags expected in source-git: {expected_tags_set}")

        src_git_project = self.cfg.src_git_svc.get_project(
            repo=project, namespace=self.cfg.src_git_namespace
        )
        # Get tags from source-git
        try:
            src_git_tags = set(tag.name for tag in src_git_project.get_tags())
        except GitlabGetError as ex:
            logger.info(f"Unable to obtain tags of {project}: {ex}")
            if ex.response_code == 404:
                src_git_tags = set()
            else:
                raise
        logger.debug(f"Current tags in source-git: {src_git_tags}")
        missing_tags = expected_tags_set - src_git_tags
        logger.debug(f"Tags missing from source-git: {missing_tags}")
        return [expected_tags[tag] for tag in missing_tags]

    def _create_task(self, project: PagureProject, branch: str, commit: str):
        """create a task to update selected (project, branch, commit)"""
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
        r = celery_app.send_task(
            name=task_name,
            expires=self.cfg.update_task_expires,
            kwargs={"event": event},
        )
        logger.info(f"Task UUID={r.id} sent to Celery.")
        Pushgateway().push_created_update_task()
