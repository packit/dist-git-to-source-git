"""
Jirka says projects shouldn't have utils.py (͡°͜ʖ͡°)
"""
import subprocess


def clone_package(
    package_name: str,
    dist_git_path: str,
    branch: str = "c8s",
    namespace: str = "rpms",
    stg: bool = False,
):
    """
    clone selected package from git.[stg.]centos.org
    """
    subprocess.check_call(
        [
            "git",
            "clone",
            "-b",
            branch,
            f"https://git{'.stg' if stg else ''}.centos.org/{namespace}/{package_name}.git",
            dist_git_path,
        ]
    )


def clone_fedora_package(
    package_name: str,
    dist_git_path: str,
    branch: str = "c8s",
    namespace: str = "rpms",
    stg: bool = False,
):
    """
    clone selected package from Fedora's src.fedoraproject.org
    """
    subprocess.check_call(
        [
            "git",
            "clone",
            "-b",
            branch,
            f"https://src{'.stg' if stg else ''}.fedoraproject.org/{namespace}/{package_name}.git",
            dist_git_path,
        ]
    )
