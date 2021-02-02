# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from os import getenv
from logging import getLogger

logger = getLogger(__name__)


class only_once(object):
    """
    Use as a function decorator to run function only once.
    """

    def __init__(self, func):
        self.func = func
        self.__name__ = func.__name__
        self.already_called = False

    def __call__(self, *args, **kwargs):
        if self.already_called:
            logger.debug(f"Function {self.func.__name__} already called. Skipping.")
            return

        self.already_called = True
        logger.debug(
            f"Function {self.func.__name__} called for the first time with "
            f"args: {args} and kwargs: {kwargs}"
        )
        return self.func(*args, **kwargs)


class if_sentry_is_enabled:
    """Run the function only if the env vars to configure Sentry are set."""

    def __init__(self, func):
        self.func = func
        self.__name__ = func.__name__
        self.configured = getenv("SENTRY_DSN") or getenv("DEPLOYMENT")
        if not self.configured:
            logger.warning("$SENTRY_DSN or $DEPLOYMENT not set")

    def __call__(self, *args, **kwargs):
        if self.configured:
            return self.func(*args, **kwargs)
        else:
            logger.debug(
                f"Sentry is not configured, don't call {self.func.__name__!r}."
            )
