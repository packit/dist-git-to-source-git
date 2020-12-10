# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import os

from pathlib import Path
from ogr import PagureService


class Configuration:
    def __init__(self):
        self.workdir = Path(os.getenv("D2S_WORKDIR", "/workdir"))
        self.dist_git_host = os.getenv("D2S_DIST_GIT_HOST", "git.centos.org")
        self.src_git_host = os.getenv("D2S_SRC_GIT_HOST", "git.stg.centos.org")
        self.src_git_token = os.getenv("D2S_SRC_GIT_TOKEN")
        self.dist_git_token = os.getenv("D2S_DIST_GIT_TOKEN")
        self.dist_git_namespace = os.getenv("D2S_DIST_GIT_NAMESPACE", "rpms")
        self.src_git_namespace = os.getenv("D2S_SRC_GIT_NAMESPACE", "source-git")
        self.branches_watched = os.getenv("D2S_BRANCHES_WATCHED", "c8s,c8").split(",")
        self.update_task_expires = os.getenv("D2S_UPDATE_TASK_EXPIRES")
        if self.update_task_expires is not None:
            self.update_task_expires = int(self.update_task_expires)

        self._src_git_svc = None
        self._dist_git_svc = None

    @property
    def src_git_svc(self) -> PagureService:
        if self._src_git_svc is None:
            self._src_git_svc = PagureService(
                instance_url=f"https://{self.src_git_host}", token=self.src_git_token
            )
        return self._src_git_svc

    @property
    def dist_git_svc(self) -> PagureService:
        if self._dist_git_svc is None:
            self._dist_git_svc = PagureService(
                instance_url=f"https://{self.dist_git_host}", token=self.dist_git_token
            )
        return self._dist_git_svc
