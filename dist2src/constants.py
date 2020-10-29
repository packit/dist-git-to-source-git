# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
"""
This module covers integration between external entities
and emulates functionality... just kidding, it's just constants.
"""
from typing import Iterable, Dict, Any

# These packages have complex %prep's which cannot be turned
# into a proper source-git repo - hence we just run the %prep
# and initiate a single-commit repo for these.
# Numbers in comments are issues in this repo.
VERY_VERY_HARD_PACKAGES: Iterable[str] = (
    "gcc",  # missing deps: docbook5-style-xsl
    "hyperv-daemons",
    "kernel",
    "libreport",  # missing deps: libtar-devel, satyr-devel
    "abrt",  # #49
    "binutils",  # #97
    "ca-certificates",  # #92
    "coreutils",  # #86
    "freeradius",  # #111
    "ksh",  # #56
    "libreport",  # #49
    "libsemanage",  # #97
    "libselinux",  # #97
    "nspr",  # #85
    "nss",  # #97, #58
    "openldap",  # #92, #58
    "openssh",  # #58
    "openssl",  # #86
    "pam",  # #86
    "policycoreutils",  # #55
    "samba",  # #72
    "satyr",  # #49
    "tzdata",  # #85
    "tog-pegasus",  # #86
    "unbound",  # #58
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
