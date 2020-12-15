# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import os

from flexmock import flexmock

from dist2src.worker.updater import Updater
from dist2src.worker.monitoring import Pushgateway
from dist2src.worker.celerizer import celery_app


def test_get_out_of_date_branches():
    """
    Dist-git branches for which there is no git tag in their source-git
    repository counterpart matching the hash of their HEAD,
    should be considered as the ones needing an update.
    """
    dist_git_svc = flexmock(api_url="https://git.centos.org/api/0/")
    src_git_svc = flexmock()
    config = flexmock(
        branches_watched=["c8", "c8s"],
        dist_git_svc=dist_git_svc,
        src_git_svc=src_git_svc,
        dist_git_namespace="rpms",
        src_git_namespace="source-git",
    )
    dist_git_branches = {
        "branches": {
            "c4": "d8483c0b65d1da97d40239264f5b707c80f5636b",  # branch not watched
            "c8": "fa4074d481e8088a1b9167f1b3d2318dd29604a0",  # out-of-date
            "c8s": "09f7b3ee8f059266b461159dd91056a573365bee",  # up-to-date
        },
        "total_branches": 10,
    }
    src_git_tags = [
        flexmock(name="c8-source-git"),
        flexmock(name="c8s-source-git"),
        flexmock(name="convert/c8/043c57dad5c7665b0cdb553e561dc55b3c676999"),
        flexmock(name="convert/c8s/09f7b3ee8f059266b461159dd91056a573365bee"),
        flexmock(name="sg-start"),
    ]
    (
        dist_git_svc.should_receive("call_api")
        .with_args(
            f"{dist_git_svc.api_url}{config.dist_git_namespace}/rsync/git/branches",
            params={"with_commits": True},
        )
        .and_return(dist_git_branches)
        .once()
    )
    src_git_project = flexmock()
    (
        src_git_svc.should_receive("get_project")
        .with_args(namespace=config.src_git_namespace, repo="rsync")
        .and_return(src_git_project)
        .once()
    )
    src_git_project.should_receive("get_tags").and_return(src_git_tags).once()

    out_of_date_branches = sorted(
        Updater(configuration=config)._out_of_date_branches("rsync")
    )
    assert out_of_date_branches == [("c8", "fa4074d481e8088a1b9167f1b3d2318dd29604a0")]


def test_no_celery_task():
    """
    If the 'CELERY_TASK_NAME' env var is not set, not tasks are sent to the
    Celery queue.
    """
    (
        flexmock(os)
        .should_receive("getenv")
        .with_args("CELERY_TASK_NAME")
        .and_return(None)
        .once()
    )
    flexmock(celery_app).should_receive("send_task").never()
    updater = Updater(configuration=flexmock())
    updater._create_task(flexmock(), "branch", "some_commit")


def test_create_celery_task():
    """
    If the 'CELERY_TASK_NAME' env var is set, a the correct Celery task with the right
    payload should be sent.
    """
    (
        flexmock(os)
        .should_receive("getenv")
        .with_args("CELERY_TASK_NAME")
        .and_return("task.dist2src.process_message")
        .ordered()
    )
    # Further 'getenv' calls to configure the celery_app
    (flexmock(os).should_receive("getenv"))
    payload = {
        "repo": {
            "fullname": "rpms/rsync",
            "name": "rsync",
        },
        "branch": "c8s",
        "end_commit": "end_commit",
    }
    (
        flexmock(celery_app)
        .should_receive("send_task")
        .with_args(
            name="task.dist2src.process_message",
            expires=3600,
            kwargs={"event": payload},
        )
        .and_return(flexmock(id="task_uuid"))
        .once()
    )
    flexmock(Pushgateway).should_receive("push_created_update_task").once()
    updater = Updater(configuration=flexmock(update_task_expires=3600))
    updater._create_task(
        flexmock(
            full_repo_name=payload["repo"]["fullname"], repo=payload["repo"]["name"]
        ),
        payload["branch"],
        payload["end_commit"],
    )


def test_check_updates():
    """
    Each project in the source-git namespace is checked whether is up to date.
    A Celery task is created for each out-of-date branch in these projects.
    """
    src_git_svc = flexmock(api_url="https://git.centos.org/api/0/")
    dist_git_svc = flexmock(api_url="https://git.centos.org/api/0/")
    config = flexmock(
        src_git_namespace="source-git",
        src_git_svc=src_git_svc,
        dist_git_svc=dist_git_svc,
        dist_git_namespace="rpms",
        dist_git_host="git.centos.org",
        branches_watched=["c8", "c8s"],
        update_task_expires=3600,
    )
    responses = [
        {
            "pagination": {"next": "https://next.page?param=value", "pages": 2},
            "projects": [
                {"name": "acl"},
                {"name": "rsync"},
            ],
        },
        {
            "pagination": {"next": None, "pages": 2},
            "projects": [
                {"name": "kernel"},
                {"name": "systemd"},
            ],
        },
    ]
    # projects are retrieved until there is a 'next' page
    (
        src_git_svc.should_receive("call_api")
        .with_args(
            f"{src_git_svc.api_url}projects",
            params={
                "namespace": config.src_git_namespace,
                "pattern": None,
                "fork": False,
                "per_page": 100,
                "owner": None,
                "short": True,
            },
        )
        .and_return(responses[0])
    )
    (
        src_git_svc.should_receive("call_api")
        .with_args(f"{responses[0]['pagination']['next']}", params=None)
        .and_return(responses[1])
    )
    mock_rsync_project = flexmock()
    dist_git_projects = {
        "acl": flexmock(),
        "rsync": mock_rsync_project,
        "kernel": flexmock(full_repo_name="rpms/kernel"),
        "systemd": flexmock(),
    }

    # each corresponding dist-git project is checked if it exists
    for project in ["acl", "rsync", "kernel", "systemd"]:
        (
            dist_git_svc.should_receive("get_project")
            .with_args(namespace=config.dist_git_namespace, repo=project)
            .and_return(dist_git_projects[project])
        )
        (
            dist_git_projects[project]
            .should_receive("exists")
            .and_return(project != "kernel")
        )

    # out-of-date branches are only checked if a dist-git repo counterpart exists
    for project in ["acl", "rsync", "systemd"]:
        (
            flexmock(Updater)
            .should_receive("_out_of_date_branches")
            .with_args(project, None)
            .and_return([] if project != "rsync" else [("c8s", "commit_hash")])
        )
    # tasks are only created for out-of-date projects
    flexmock(Updater).should_receive("_create_task").with_args(
        mock_rsync_project, "c8s", "commit_hash"
    ).once()
    # source-git repos without a dist-git counterpart are monitored
    flexmock(Pushgateway).should_receive("push_found_missing_dist_git_repo").once()

    Updater(configuration=config).check_updates()
