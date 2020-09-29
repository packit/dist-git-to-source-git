# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from logging import getLogger
from os import getenv

from dist2src.worker.decorators import only_once

logger = getLogger(__name__)


@only_once
def configure_sentry(runner_type: str) -> None:
    logger.debug("Setting up Sentry")

    if not getenv("SENTRY_DSN") or not getenv("DEPLOYMENT"):
        logger.warning("$SENTRY_DSN or $DEPLOYMENT not set")
        return

    # so that we don't have to have sentry sdk installed locally
    from sentry_sdk import init, configure_scope
    from sentry_sdk.integrations.celery import CeleryIntegration

    init(
        dsn=getenv("SENTRY_DSN"),
        integrations=[CeleryIntegration()],
        environment=getenv("DEPLOYMENT"),
    )
    with configure_scope() as scope:
        scope.set_tag("runner-type", runner_type)
