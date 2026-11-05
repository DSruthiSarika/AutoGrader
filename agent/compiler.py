
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


DOCKER_IMAGE = "gcc:latest"


def compile_c_program(source_file, compiler=None, timeout_seconds=30):
    """
    Compile a C source file into a Linux executable using Docker GCC.

    The caller is responsible for deleting the generated executable.
    """

    source_path = Path(source_file).resolve()

    if not source_path.is_file():
        return {
            "success": False,
            "executable": None,
            "error": f"Source file not found: {source_path}",
        }

    docker = shutil.which("docker")

    if not docker:
        return {
            "success": False,
            "executable": None,
            "error": "Docker CLI was not found.",
        }

    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ):
        return {
            "success": False,
            "executable": None,
            "error": "Compilation timeout must be positive.",
        }

    executable_path = None

    try:
        fd, executable_name = tempfile.mkstemp(
            prefix=f"{source_path.stem}_autograder_",
            dir=str(source_path.parent),
        )
        os.close(fd)

        executable_path = Path(executable_name)
        executable_path.unlink()

        command = [
            docker,
            "run",
            "--rm",
            "--network=none",
            "-v",
            f"{source_path.parent}:/work",
            "-w",
            "/work",
            DOCKER_IMAGE,
            "gcc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            source_path.name,
            "-o",
            executable_path.name,
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        if result.returncode != 0:
            executable_path.unlink(missing_ok=True)

            return {
                "success": False,
                "executable": None,
                "error": result.stderr or result.stdout,
                "command": command,
            }

        if not executable_path.is_file():
            return {
                "success": False,
                "executable": None,
                "error": "Docker compilation succeeded but executable was not created.",
            }

        executable_path.chmod(0o755)

        return {
            "success": True,
            "executable": str(executable_path),
            "error": None,
            "warnings": result.stderr,
            "command": command,
            "compiler": "Docker GCC",
        }

    except subprocess.TimeoutExpired:
        if executable_path:
            executable_path.unlink(missing_ok=True)

        return {
            "success": False,
            "executable": None,
            "error": f"Compilation timed out after {timeout_seconds} seconds.",
        }

    except OSError as exc:
        if executable_path:
            executable_path.unlink(missing_ok=True)

        return {
            "success": False,
            "executable": None,
            "error": str(exc),
        }
