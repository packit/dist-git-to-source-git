# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from os import getenv

from celery import Celery
from dist2src.worker.sentry import configure_sentry
from lazy_object_proxy import Proxy


class Celerizer:
    def __init__(self):
        self._celery_app = None

    @property
    def celery_app(self):
        if self._celery_app is None:
            host = getenv("REDIS_SERVICE_HOST", "redis")
            password = getenv("REDIS_PASSWORD", "")
            port = getenv("REDIS_SERVICE_PORT", "6379")
            db = getenv("REDIS_SERVICE_DB", "0")
            broker_url = f"redis://:{password}@{host}:{port}/{db}"

            self._celery_app = Celery(broker=broker_url)
        return self._celery_app


def get_celery_application():
    configure_sentry(runner_type="worker")
    return Celerizer().celery_app


celery_app: Celery = Proxy(get_celery_application)
