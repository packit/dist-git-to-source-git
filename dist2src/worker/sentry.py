# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from logging import getLogger
from os import getenv

from dist2src.worker.decorators import only_once, if_sentry_is_enabled

logger = getLogger(__name__)


@only_once
@if_sentry_is_enabled
def configure_sentry(runner_type: str) -> None:
    logger.debug("Setting up Sentry")

    # so that we don't have to have sentry sdk installed locally
    from sentry_sdk import init, configure_scope
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.logging import ignore_logger

    init(
        dsn=getenv("SENTRY_DSN"),
        integrations=[CeleryIntegration()],
        environment=getenv("DEPLOYMENT"),
    )
    with configure_scope() as scope:
        scope.set_tag("runner-type", runner_type)

    # Ignore the error logs from the 'rpmbuild' command
    ignore_logger("dist2src.core.rpmbuild")


@if_sentry_is_enabled
def set_tag(key: str, value: str) -> None:
    # so that we don't have to have sentry sdk installed locally
    import sentry_sdk

    sentry_sdk.set_tag(key, value)
