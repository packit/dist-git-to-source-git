# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

ARG base_image=centos:8
ARG package_manager
FROM $base_image

ENV package_manager ${package_manager:-yum -y}
RUN $package_manager -y install gcc git krb5-devel python38-devel python38-pip rpm-build && $package_manager -y clean all
RUN curl --output /usr/bin/get_sources.sh https://git.centos.org/centos-git-common/raw/master/f/get_sources.sh && chmod +x /usr/bin/get_sources.sh
# Tools required by the %prep section of some packages
RUN $package_manager -y install \
    bison \
    flex \
    make \
    autoconf \
    automake \
    python3-rpm \
    && $package_manager -y clean all \
    && pip3.8 install ipdb

# pretty naive, but works - building python3-rpm for 3.8 is very very hard, b/c you need to rebuild
# everything - rpm, dnf, ...
RUN ln -s /usr/lib64/python3.6/site-packages/rpm /usr/lib64/python3.8/site-packages/rpm

RUN git config --system user.name "Packit" && git config --system user.email "packit"
COPY .git /src/.git
COPY dist2src /src/dist2src
COPY README.md setup.cfg setup.py /src/

WORKDIR /src
# TODO install dependencies from RPM, if possible
RUN pip3.8 install .

WORKDIR /workdir
VOLUME /workdir

COPY macros.packit /usr/lib/rpm/macros.d/macros.packit
COPY packitpatch /usr/bin/packitpatch

ENTRYPOINT ["dist2src"]
