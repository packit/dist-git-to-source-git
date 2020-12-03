# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import re


def singular_fork(pagure_namespace: str) -> str:
    # When the namespace is a fork, "fork" is singular when accessing
    # the API, but plural in the Git URLs.
    # Keep this here, so we can test with forks.
    return re.sub(r"^forks\/", "fork/", pagure_namespace)
