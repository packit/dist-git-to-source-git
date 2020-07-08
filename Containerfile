ARG base_image=centos:8
ARG package_manager
FROM $base_image

ENV package_manager ${package_manager:-yum -y}
RUN $package_manager -y install gcc git krb5-devel python3-devel python3-pip rpm-build && $package_manager -y clean all 
RUN curl --output /usr/bin/get_sources.sh https://git.centos.org/centos-git-common/raw/master/f/get_sources.sh && chmod +x /usr/bin/get_sources.sh
COPY ./ /src

WORKDIR /src
RUN pip3 install .

WORKDIR /workdir
VOLUME /workdir

ENTRYPOINT ["dist2src"]
