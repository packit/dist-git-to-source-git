# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

ARG base_image=centos:8
ARG package_manager
FROM $base_image

ENV LANG=en_US.UTF-8 \
    ANSIBLE_PYTHON_INTERPRETER=/usr/bin/python3 \
    ANSIBLE_STDOUT_CALLBACK=debug \
    USER=packit \
    HOME=/home/packit \
    package_manager=${package_manager:-"yum -y"}

RUN $package_manager install epel-release \
    && $package_manager install ansible

# installing as many (setup.cfg) deps from RPM as possible
RUN $package_manager install \
    rpm-build \
    python3-GitPython \
    python3-celery \
    python3-redis \
    python3-lazy-object-proxy \
    python3-timeout-decorator
# ogr & packitos deps as RPMs
RUN $package_manager install \
    python3-bodhi-client \
    python3-cccolutils \
    python3-copr \
    python3-gitlab \
    python3-gnupg \
    python3-jwt \
    python3-marshmallow-enum \
    python3-pam \
    python3-sh \
    python3-tabulate \
    python3-wrapt

# Tools required by the %prep section of some packages
RUN $package_manager install \
    bison \
    flex \
    make \
    autoconf \
    automake \
    gettext-devel \
    sscg \
    libtool \
    dos2unix \
    perl-devel \
    rubygems \
    xmlto
# PowerTools repo installed for gtk-doc
RUN $package_manager install dnf-plugins-core \
    && $package_manager config-manager --set-enabled PowerTools \
    && $package_manager --enablerepo=PowerTools --setopt=PowerTools.module_hotfixes=true install javapackages-local gtk-doc

# debugging, tests (pytest is installed from PyPI since RPM contains ancient v3.4.2)
RUN $package_manager install python3-ipython
RUN pip3 install ipdb pytest flexmock && pip3 check

RUN curl --output /usr/bin/get_sources.sh https://git.centos.org/centos-git-common/raw/master/f/get_sources.sh && chmod +x /usr/bin/get_sources.sh

# https://stackoverflow.com/questions/6842687/the-remote-end-hung-up-unexpectedly-while-git-cloning
# we are unable to clone kernel, hence the postBuffer thingy
RUN git config --system user.name "Packit" \
    && git config --system user.email "packit" \
    && git config --system http.postBuffer 1048576000

COPY macros.packit /usr/lib/rpm/macros.d/macros.packit
COPY packitpatch /usr/bin/packitpatch

COPY README.md setup.cfg setup.py files/gitconfig files/run_worker.sh /src/
COPY dist2src /src/dist2src
# setuptools-scm
COPY .git /src/.git

WORKDIR /src
RUN pip3 install . && pip3 check

WORKDIR /workdir
VOLUME /workdir

# Celery worker which runs tasks from centosmsg listener
COPY files/install-deps-worker.yml /src/
RUN ansible-playbook -vv -c local -i localhost, /src/install-deps-worker.yml
COPY files/recipe-worker.yml /src/
RUN ansible-playbook -vv -c local -i localhost, /src/recipe-worker.yml

CMD ["dist2src"]
