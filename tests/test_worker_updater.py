# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import os

from flexmock import flexmock

from dist2src.worker import sentry
from dist2src.worker.updater import Updater
from dist2src.worker.monitoring import Pushgateway
from dist2src.worker.celerizer import celery_app


def test_get_out_of_date_branches():
    """
    Dist-git branches for which there is no git tag in their source-git
    repository counterpart matching the hash of their HEAD,
    should be considered as the ones needing an update.
    """
    project_name = "rsync"
    dist_git_svc = flexmock(api_url="https://git.centos.org/api/0/")
    src_git_svc = flexmock()
    config = flexmock(
        branches_watched=["c8", "c8s"],
        dist_git_svc=dist_git_svc,
        src_git_svc=src_git_svc,
        dist_git_namespace="rpms",
        src_git_namespace="redhat/centos-stream/src",
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
            f"{dist_git_svc.api_url}{config.dist_git_namespace}/{project_name}/git/branches",
            params={"with_commits": True},
        )
        .and_return(dist_git_branches)
        .once()
    )
    src_git_project = flexmock(repo=project_name)
    src_git_project.should_receive("get_tags").and_return(src_git_tags).once()

    out_of_date_branches = sorted(
        Updater(configuration=config)._get_out_of_date_branches(src_git_project)
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
    src_git_namespace = "redhat/centos-stream/src"
    gitlab_groups = flexmock()
    gitlab_instance = flexmock(groups=gitlab_groups)
    src_git_svc = flexmock(
        instance_url="https://git.centos.org/api/0/", gitlab_instance=gitlab_instance
    )
    dist_git_svc = flexmock(api_url="https://git.centos.org/api/0/")
    config = flexmock(
        src_git_namespace=src_git_namespace,
        src_git_svc=src_git_svc,
        dist_git_svc=dist_git_svc,
        dist_git_namespace="rpms",
        dist_git_host="git.centos.org",
        branches_watched=["c8", "c8s"],
        update_task_expires=3600,
    )
    gitlab_projects = flexmock()
    src_gitlab_group = flexmock(projects=gitlab_projects)
    gitlab_groups.should_receive("get").and_return(src_gitlab_group)
    gitlab_projects.should_receive("list").with_args(page=1, per_page=100).and_return(
        [
            flexmock(name="acl"),
            flexmock(name="rsync"),
            flexmock(name="kernel"),
            flexmock(name="systemd"),
        ]
    )
    src_project_rsync = flexmock(repo="rsync")
    gitlab_projects.should_receive("list").with_args(page=2, per_page=100).and_return(
        []
    )
    src_git_svc.should_receive("get_project").with_args(
        repo="acl", namespace=src_git_namespace
    ).and_return(flexmock(repo="acl"))
    src_git_svc.should_receive("get_project").with_args(
        repo="rsync", namespace=src_git_namespace
    ).and_return(src_project_rsync)
    src_git_svc.should_receive("get_project").with_args(
        repo="kernel", namespace=src_git_namespace
    ).and_return(flexmock(repo="kernel"))
    src_git_svc.should_receive("get_project").with_args(
        repo="systemd", namespace=src_git_namespace
    ).and_return(flexmock(repo="systemd"))
    flexmock(sentry).should_receive("configure_sentry").once()
    # projects are retrieved until there is a 'next' page
    dist_project_rsync = flexmock()
    dist_git_projects = {
        "acl": flexmock(),
        "rsync": dist_project_rsync,
        "kernel": flexmock(full_repo_name="rpms/kernel"),
        "systemd": flexmock(),
    }

    # each corresponding dist-git project is checked if it exists
    for project in ["acl", "rsync", "kernel", "systemd"]:
        (
            dist_git_svc.should_receive("get_project")
            .with_args(
                namespace=config.dist_git_namespace, repo=project, username="packit"
            )
            .and_return(dist_git_projects[project])
        )
        (
            dist_git_projects[project]
            .should_receive("exists")
            .and_return(project != "kernel")
        )

    # return empty list for all except rsync, order of these mocks is important!
    (flexmock(Updater).should_receive("_get_out_of_date_branches").and_return([]))
    (
        flexmock(Updater)
        .should_receive("_get_out_of_date_branches")
        .with_args(src_project_rsync, None)
        .and_return([("c8s", "commit_hash")])
    )
    # tasks are only created for out-of-date projects
    flexmock(Updater).should_receive("_create_task").with_args(
        dist_project_rsync, "c8s", "commit_hash"
    ).once()
    # source-git repos without a dist-git counterpart are monitored
    flexmock(Pushgateway).should_receive("push_found_missing_dist_git_repo").once()
    # finishing the check-update process is monitored
    flexmock(Pushgateway).should_receive(
        "push_dist2src_finished_checking_updates"
    ).once()

    Updater(configuration=config).check_updates()
