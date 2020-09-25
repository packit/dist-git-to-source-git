# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from os import getenv
from typing import Optional

from dist2src.worker.celerizer import celery_app
from dist2src.worker.processor import Processor

task_name = getenv("CELERY_TASK_NAME", "task.dist2src.process_message")


@celery_app.task(name=task_name)
def process_message(event: dict, **kwargs) -> Optional[dict]:
    return Processor().process_message(event=event)
