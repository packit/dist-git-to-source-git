# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
"""
This module covers integration between external entities
and emulates functionality... just kidding, it's just constants.
"""
from typing import Iterable, Dict, Any

# these packages have complex %prep's which cannot be turned
# into a proper source-git repo - hence we just run the %prep
# and initiate a single-commit repo for these
VERY_VERY_HARD_PACKAGES: Iterable[str] = (
    "gcc",
    "hyperv-daemons",
    "kernel",
    "libreport",
)

# build and test targets
TARGETS = ["centos-stream-x86_64"]
START_TAG = "sg-start"
POST_CLONE_HOOK = "post-clone"
AFTER_PREP_HOOK = "after-prep"
TEMP_SG_BRANCH = "updates"

HOOKS: Dict[str, Dict[str, Any]] = {
    "kernel": {
        # %setup -c creates another directory level but patches don't expect it
        AFTER_PREP_HOOK: (
            "set -e; "
            "shopt -s dotglob nullglob && "  # so that * would match dotfiles as well
            "cd BUILD/kernel-4.18.0-*.el8/ && "
            "mv ./linux-4.18.0-*.el8.x86_64/* . && "
            "rmdir ./linux-4.18.0-*.el8.x86_64"
        )
    },
}
