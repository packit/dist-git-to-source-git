import logging
import os

from prometheus_client import CollectorRegistry, Counter, push_to_gateway

logger = logging.getLogger(__name__)


class Pushgateway:
    def __init__(self):
        self.pushgateway_address = os.getenv(
            "PUSHGATEWAY_ADDRESS", "http://pushgateway"
        )
        self.registry = CollectorRegistry()

        # metrics
        self.received_messages = Counter(
            "received_messages",
            "Number of received messages from listener",
            ["result"],
            registry=self.registry,
        )

        self.created_updates = Counter(
            "created_updates",
            "Number of created updates",
            registry=self.registry,
        )

    def push(self):
        if not self.pushgateway_address:
            logger.debug("Pushgateway address not defined.")
            return

        push_to_gateway(
            self.pushgateway_address, job="dist2src-update", registry=self.registry
        )

    def push_created_update(self):
        self.created_updates.inc()
        self.push()

    def push_received_message(self, ignored: bool):
        self.received_messages.labels(
            result="ignored" if ignored else "not_ignored"
        ).inc()
        self.push()
