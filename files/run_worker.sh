#!/usr/bin/bash

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

# concurrency: Number of concurrent worker processes/threads/green threads executing tasks.
# prefetch-multiplier: How many messages to prefetch at a time multiplied by the number of concurrent processes.
# http://docs.celeryproject.org/en/latest/userguide/optimizing.html#prefetch-limits
exec celery worker --app="${APP}" --loglevel=${LOGLEVEL} --concurrency=1 --prefetch-multiplier=1
