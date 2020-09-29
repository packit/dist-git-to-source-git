# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from logging import getLogger

logger = getLogger(__name__)


class only_once(object):
    """
    Use as a function decorator to run function only once.
    """

    def __init__(self, func):
        self.func = func
        self.configured = False

    def __call__(self, *args, **kwargs):
        if self.configured:
            logger.debug(f"Function {self.func.__name__} already called. Skipping.")
            return

        self.configured = True
        logger.debug(
            f"Function {self.func.__name__} called for the first time with "
            f"args: {args} and kwargs: {kwargs}"
        )
        return self.func(*args, **kwargs)
