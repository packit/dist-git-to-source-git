# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import os
import logging
import shutil
import git

from flexmock import flexmock
from pathlib import Path
from ogr import PagureService
from dist2src.worker.processor import Processor
from dist2src.worker.monitoring import Pushgateway
from dist2src.worker import processor
from dist2src.core import Dist2Src


def test_event_not_for_dist_git_namespace(caplog):
    """
    When the update event not from the configured dist-git namespace,
    the event is ignored and the logs indicate this.
    """
    (
        flexmock(os)
        .should_receive("getenv")
        .with_args("D2S_DIST_GIT_NAMESPACE", "rpms")
        .and_return("rpms")
    )
    flexmock(os).should_receive("getenv").and_return("blah")
    flexmock(Dist2Src).should_receive("convert").never()
    flexmock(Pushgateway).should_receive("push_received_message").with_args(
        ignored=True
    ).once()

    with caplog.at_level(logging.INFO):
        Processor().process_message(
            {"repo": {"fullname": "tests/acl", "name": "acl"}, "branch": "c8s"}
        )
        assert "Ignore update event for tests/acl" in caplog.text


def test_event_not_for_branch(caplog):
    """
    When the update event not for the configured branch,
    the event is ignored and the logs indicate this.
    """
    flexmock(Dist2Src).should_receive("convert").never()
    flexmock(Pushgateway).should_receive("push_received_message").with_args(
        ignored=True
    ).once()

    with caplog.at_level(logging.INFO):
        Processor().process_message(
            {"repo": {"fullname": "rpms/acl", "name": "acl"}, "branch": "work"}
        )
        assert "Ignore update event for rpms/acl" in caplog.text
        assert "Branch 'work' is not one of the watched branches" in caplog.text


def test_no_corresponding_source_git(caplog):
    """
    When there is no corresponding source-git project,
    no conversion takes place and the logs indicate that the event
    was ignored.
    """
    project = flexmock()
    (
        flexmock(PagureService)
        .should_receive("get_project")
        .with_args(namespace="source-git", repo="acl")
        .and_return(project)
    )
    project.should_receive("exists").and_return(False)
    flexmock(Pushgateway).should_receive("push_received_message").with_args(
        ignored=True
    ).once()
    flexmock(Dist2Src).should_receive("convert").never()

    with caplog.at_level(logging.INFO):
        Processor().process_message(
            {"repo": {"fullname": "rpms/acl", "name": "acl"}, "branch": "c8s"}
        )
        assert "Ignore update event for rpms/acl" in caplog.text


def test_conversion(caplog):
    """
    When the branch and repository needs to be updated, conversion is triggered.
    """
    # Source-git project exists.
    project = flexmock()
    (
        flexmock(PagureService)
        .should_receive("get_project")
        .with_args(namespace="source-git", repo="acl")
        .and_return(project)
    )
    project.should_receive("exists").and_return(True)

    # Previous working directories are cleaned up.
    flexmock(shutil).should_receive("rmtree")
    # Dist-git repo is cloned and the branch is checked out.
    dist_git_repo = flexmock(
        git=flexmock(), branches={"c8s": flexmock(commit=flexmock(hexsha="0a0c838"))}
    )
    (
        flexmock(git.Repo)
        .should_receive("clone_from")
        .with_args("https://git.centos.org/rpms/acl.git", Path("/workdir/rpms/acl"))
        .and_return(dist_git_repo)
        .once()
        .ordered()
    )
    dist_git_repo.git.should_receive("checkout").with_args("c8s").ordered()

    # Source-git repo is cloned and the branch is checked out.
    project.should_receive("get_git_urls").and_return(
        {"ssh": "ssh://git@git.stg.centos.org"}
    )
    src_git_repo = flexmock(git=flexmock(), references=[flexmock(remote_head="c8s")])
    (
        flexmock(git.Repo)
        .should_receive("clone_from")
        .with_args("ssh://git@git.stg.centos.org", Path("/workdir/source-git/acl"))
        .and_return(src_git_repo)
        .once()
        .ordered()
    )
    src_git_repo.git.should_receive("checkout").with_args("c8s").ordered()

    # Conversion is run.
    d2s = flexmock()
    (
        flexmock(processor)
        .should_receive("Dist2Src")
        .with_args(
            dist_git_path=Path("/workdir/rpms/acl"),
            source_git_path=Path("/workdir/source-git/acl"),
        )
        .and_return(d2s)
    )
    d2s.should_receive("convert").with_args("c8s", "c8s")
    # Result is pushed.
    src_git_repo.git.should_receive("push").with_args(
        "origin", "c8s", tags=True, force=True
    ).once()

    flexmock(Pushgateway).should_receive("push_received_message").with_args(
        ignored=False
    ).once()
    flexmock(Pushgateway).should_receive("push_created_update").once()

    Processor().process_message(
        {
            "repo": {"fullname": "rpms/acl", "name": "acl"},
            "branch": "c8s",
            "end_commit": "0a0c838",
        }
    )
