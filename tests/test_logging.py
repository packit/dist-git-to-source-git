import os

from pathlib import Path
from dist2src.worker.logging import set_logging_to_file


def test_set_logging_to_file(tmpdir):
    set_logging_to_file("acl", "00ab78", Path(tmpdir))

    expected_dir = Path(tmpdir / "acl")
    assert expected_dir.is_dir()

    files = os.listdir(expected_dir)
    assert len(files) == 1

    file = files[0]
    assert file.startswith("00ab78_")
