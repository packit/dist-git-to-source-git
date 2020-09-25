# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from logging import getLogger
from typing import Optional

logger = getLogger(__name__)


class Processor:
    def process_message(self, event: dict, **kwargs) -> Optional[dict]:
        logger.info(f"Processing message with {event}")
        return None
