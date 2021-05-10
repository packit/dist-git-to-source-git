#!/usr/bin/bash

set -eu

# $APP defines where's the module (or package)
if [[ -z ${APP} ]]; then
    echo "APP not defined or empty, exiting"
    exit 1
fi

if [[ -z ${DEPLOYMENT} ]]; then
    echo "$DEPLOYMENT not defined or empty, exiting"
    exit 1
elif [[ ${DEPLOYMENT} == "prod" ]]; then
  LOGLEVEL="INFO"
else
  LOGLEVEL="DEBUG"
fi

source /src/setup_env_in_openshift.sh

DEFAULT_DISTGIT_HOST="git.centos.org"
D2S_DIST_GIT_HOST="${D2S_DIST_GIT_HOST:-$DEFAULT_DISTGIT_HOST}"
DEFAULT_SRC_HOST="gitlab.com"
D2S_SRC_GIT_HOST="${D2S_SRC_GIT_HOST:-$DEFAULT_SRC_HOST}"

mkdir --mode=0700 -p "${HOME}/.ssh"
pushd "${HOME}/.ssh"
install -m 0600 /d2s-ssh/id_rsa .
install -m 0644 /d2s-ssh/id_rsa.pub .
grep -q "${D2S_DIST_GIT_HOST}" known_hosts || ssh-keyscan "${D2S_DIST_GIT_HOST}" >>known_hosts
grep -q "${D2S_SRC_GIT_HOST}" known_hosts || ssh-keyscan "${D2S_SRC_GIT_HOST}" >>known_hosts
popd

# concurrency: Number of concurrent worker processes/threads/green threads executing tasks.
# prefetch-multiplier: How many messages to prefetch at a time multiplied by the number of concurrent processes.
# http://docs.celeryproject.org/en/latest/userguide/optimizing.html#prefetch-limits
exec celery worker --app="${APP}" --loglevel=${LOGLEVEL} --concurrency=1 --prefetch-multiplier=1
