import logging
from datetime import datetime
from pathlib import Path


def set_logging_to_file(
    repo_name: str, commit_sha: str, logs_dir: Path = Path("/log-files/")
):
    """
    Set logging to a file for conversion.
    :param repo_name: name of the repository
    :param commit_sha: commit SHA
    :param logs_dir: dir where the logs are stored
    :return:
    """
    logger = logging.getLogger("dist2src")
    logger.setLevel(logging.DEBUG)
    log_dir = logs_dir / repo_name
    log_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{commit_sha}_{datetime.now().isoformat(timespec='seconds')}.log"

    file_handler = logging.FileHandler(log_dir / filename)
    formatter = logging.Formatter(
        "[%(asctime)s %(filename)s %(levelname)s] %(message)s"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    logger.addHandler(file_handler)
    logger.info(f"Processing repository {repo_name}, commit SHA {commit_sha}.")
