# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
"""
This module covers integration between external entities
and emulates functionality... just kidding, it's just constants.
"""
from typing import Iterable, Dict, Any, Tuple

# These packages have complex %prep's which cannot be turned
# into a proper source-git repo - hence we just run the %prep
# and initiate a single-commit repo for these.
# Numbers in comments are issues in this repo or
# failures due to which this approach is used.
VERY_VERY_HARD_PACKAGES: Iterable[str] = (
    "abrt",  # #49
    "binutils",  # #97
    "ca-certificates",  # #92
    "coreutils",  # #86
    "freeradius",  # #111
    "gcc",  # missing deps: docbook5-style-xsl
    "geolite2",  # .git not in BUILD/
    "ghc-rpm-macros",  # .git not in BUILD/
    "hardlink",  # .git not in BUILD/
    "hyperv-daemons",  # .git not in BUILD/
    "kernel",
    "ksh",  # #56
    "libaec",  # .git not in BUILD/
    "libreport",  # #49
    "libreport",  # missing deps: libtar-devel, satyr-devel
    "libselinux",  # #97
    "libsemanage",  # #97
    "mingw-filesystem",  # .git not in BUILD/
    "multilib-rpm-config",
    "nspr",  # #85
    "nss",  # #97, #58
    "openldap",  # #92, #58
    "openssh",  # #58
    "openssl",  # #86
    "osbuild",  # .git not in BUILD/
    "pam",  # #86
    "perl-Capture-Tiny",  # .git not in BUILD/
    "perl-Class-Tiny",  # .git not in BUILD/
    "perl-Data-ICal-TimeZone",  # .git not in BUILD/
    "perl-DateTime-Format-HTTP",  # .git not in BUILD/
    "perl-DateTime-TimeZone-SystemV",  # .git not in BUILD/
    "perl-DateTime-TimeZone-Tzfile",  # .git not in BUILD/
    "perl-Devel-StackTrace",  # .git not in BUILD/
    "perl-Exporter-Tiny",  # .git not in BUILD/
    "perl-File-CheckTree",  # .git not in BUILD/
    "perl-File-Temp",  # .git not in BUILD/
    "perl-Font-TTF",  # .git not in BUILD/
    "perl-HTML-Tagset",  # .git not in BUILD/
    "perl-HTML-Tree",  # .git not in BUILD/
    "perl-IO-HTML",  # .git not in BUILD/
    "perl-IO-Socket-INET6",  # .git not in BUILD/
    "perl-IO-Tty",  # .git not in BUILD/
    "perl-LWP-MediaTypes",  # .git not in BUILD/
    "perl-Mail-IMAPTalk",  # .git not in BUILD/
    "perl-Mail-JMAPTalk",  # .git not in BUILD/
    "perl-MIME-Types",  # .git not in BUILD/
    "perl-Module-Build-Tiny",  # .git not in BUILD/
    "perl-Net-CalDAVTalk",  # .git not in BUILD/
    "perl-Net-CardDAVTalk",  # .git not in BUILD/
    "perl-Net-DAVTalk",  # .git not in BUILD/
    "perl-Net-HTTP",  # .git not in BUILD/
    "perl-Net-SMTP-SSL",  # .git not in BUILD/
    "perl-Path-Tiny",  # .git not in BUILD/
    "perl-Pod-LaTeX",  # .git not in BUILD/
    "perl-Role-Tiny",  # .git not in BUILD/
    "perl-Term-Table",  # .git not in BUILD/
    "perl-Test-TrailingSpace",  # .git not in BUILD/
    "perl-Text-Template",  # .git not in BUILD/
    "perl-Try-Tiny",  # .git not in BUILD/
    "perl-Unicode-UTF8",  # .git not in BUILD/
    "perl-XML-Filter-BufferText",  # .git not in BUILD/
    "perl-XML-Twig",  # .git not in BUILD/
    "perl-YAML-Tiny",  # .git not in BUILD/
    "policycoreutils",  # #55
    "ps_mem",  # .git not in BUILD/
    "publicsuffix-list",  # .git not in BUILD/
    "redhat-rpm-config",  # .git not in BUILD/
    "rubygem-kramdow",  # .git not in BUILD/
    "rubygem-rspec",  # .git not in BUILD/
    "rubygem-thread_order",  # .git not in BUILD/
    "samba",  # #72
    "satyr",  # #49
    "tog-pegasus",  # #86
    "tzdata",  # #85
    "unbound",  # #58
    "virtio-win",  # .git not in BUILD/
    "web-assets",  # .git not in BUILD/
    "xorg-x11-utils",  # .git not in BUILD/
)

# build and test targets
TARGETS = ["centos-stream-8-x86_64"]
START_TAG_TEMPLATE = "{branch}-source-git"
POST_CLONE_HOOK = "post-clone"
AFTER_PREP_HOOK = "after-prep"
TEMP_SG_BRANCH = "updates"
GITLAB_SRC_NAMESPACE = "redhat/centos-stream/src"

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

# These packages/branches are known to be failing when updated.
# Skip updating them until the reason is figured out.
IGNORED_PACKAGES: Iterable[Tuple[str, str]] = [
    ("boost", "c8s"),
    ("boost", "c8"),
    ("cockpit", "c8s"),
    ("cockpit-appstream", "c8s"),
    ("docbook-dtds", "c8"),
    ("gcc", "c8"),
    ("gcc", "c8s"),
    ("google-noto-cjk-fonts", "c8s"),
    ("google-noto-cjk-fonts", "c8"),
    ("google-noto-fonts", "c8"),
    ("google-noto-fonts", "c8s"),
    # https://github.com/packit/dist-git-to-source-git/issues/164
    ("go-srpm-macros", "c8s"),
    ("grafana-pcp", "c8"),
    ("grafana-pcp", "c8s"),
    ("kernel", "c8s"),
    ("kernel", "c8"),
    ("libabigail", "c8"),
    ("libbpf", "c8"),
    ("libbpf", "c8s"),
    ("libidn2", "c8"),
    ("libkkc-data", "c8"),
    ("mcelog", "c8s"),
    ("mingw-binutils", "c8s"),
    ("mingw-binutils", "c8"),
    ("mingw-gcc", "c8"),
    ("mozjs60", "c8s"),
    ("mozjs60", "c8"),
    ("nss", "c8"),
    ("nss", "c8s"),
    # https://github.com/packit/dist-git-to-source-git/issues/164
    ("osinfo-db", "c8s"),
    ("pcp", "c8"),
    ("pcp", "c8s"),
    ("pcs", "c8"),
    ("pcs", "c8s"),
    ("perl-MIME-Types", "c8s"),
    ("perl-Module-Install-AuthorTests", "c8"),
    ("python-sphinx", "c8"),
    ("rsyslog", "c8"),
    ("rsyslog", "c8s"),
    ("rubygem-kramdown", "c8"),
    ("sassc", "c8"),
    # https://github.com/packit/dist-git-to-source-git/issues/163
    ("smc-tools", "c8s"),
    ("tesseract", "c8"),
    ("trousers", "c8s"),
    ("trousers", "c8"),
    ("valgrind", "c8"),
    ("virtio-win", "c8s"),
    ("virtio-win", "c8"),
    ("wireshark", "c8"),
    ("wireshark", "c8s"),
]
