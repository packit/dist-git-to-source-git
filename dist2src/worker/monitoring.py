import logging
import os

from prometheus_client import CollectorRegistry, Counter, push_to_gateway

logger = logging.getLogger(__name__)


class Pushgateway:
    def __init__(self):
        self.pushgateway_address = os.getenv("PUSHGATEWAY_ADDRESS")
        self.registry = CollectorRegistry()

        # metrics
        self.received_messages = Counter(
            "received_messages",
            "Number of received messages from listener",
            ["result"],
            registry=self.registry,
        )

        self.abandoned_updates = Counter(
            "abandoned_updates",
            "Number of updates abandoned",
            registry=self.registry,
        )

        self.created_updates = Counter(
            "created_updates",
            "Number of created updates",
            registry=self.registry,
        )

        self.found_missing_dist_git_repo = Counter(
            "found_missing_dist_git_repo",
            "Number of dist-git repositories found missing by the scheduled updater.",
            registry=self.registry,
        )

        self.created_update_task = Counter(
            "created_update_task",
            "Number of update tasks created for out-of-date source-git repos.",
            registry=self.registry,
        )

    def push(self):
        """
        Push collected metrics to Pushgateway
        :return:
        """
        if not self.pushgateway_address:
            logger.debug("Pushgateway address not defined.")
            return

        push_to_gateway(
            self.pushgateway_address, job="dist2src-update", registry=self.registry
        )

    def push_created_update(self):
        """
        Push info about created update to Pushgateway
        :return:
        """
        self.created_updates.inc()
        self.push()

    def push_received_message(self, ignored: bool):
        """
        Push info about received message to Pushgateway
        :param ignored: whether the received message was ignored or processed
        :return:
        """
        self.received_messages.labels(
            result="ignored" if ignored else "not_ignored"
        ).inc()
        self.push()

    def push_found_missing_dist_git_repo(self):
        """
        Push info about finding a dist-git repo missing to Pushgateway
        :return:
        """
        self.found_missing_dist_git_repo.inc()
        self.push()

    def push_created_update_task(self):
        """
        Push info about creating a task to update an out-of-date
        source-git repo to Pushgateway
        :return:
        """
        self.created_update_task.inc()
        self.push()

    def push_abandoned_update(self):
        """
        Push info about abandoning an update because the dist-git repo
        has different content than the update event
        :return:
        """
        self.abandoned_updates.inc()
        self.push()
