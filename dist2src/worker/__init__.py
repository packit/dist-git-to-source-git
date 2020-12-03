# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import re


# When the namespace is a fork, "fork" is singular when accessing
# the API, but plural in the Git URLs.
# Furthermore:
# - 'fullname' in mqtt messages has it in plural
# - 'fullname' in API responses has it in singular
# Use these functions to make testing with forks possible.


def singular_fork(pagure_namespace: str) -> str:
    return re.sub(r"^forks\/", "fork/", pagure_namespace)


def plural_fork(pagure_namespace: str) -> str:
    return re.sub(r"^fork\/", "forks/", pagure_namespace)
