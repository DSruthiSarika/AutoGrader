
import shutil
import subprocess
import tempfile
from pathlib import Path

from agent.execution import run_program


DOCKER_IMAGE = "gcc:latest"


def check_memory_safety(
    source_file,
    test_inputs=None,
    timeout_seconds=5,
    memory_limit_mb=128,
):
    """
    Compile and execute C programs using ASan and UBSan inside Docker.

    A clean run means no sanitizer-detectable issue was found.
    It does not prove complete memory safety.
    """

    source = Path(source_file).resolve()

    result = {
        "metric": "memory_safety",
        "source_file": str(source),
        "score": None,
        "status": "NOT_EVALUATED",
        "tests": [],
        "findings": [],
    }

    # Validate source file
    if not source.is_file():
        result["message"] = f"Source file not found: {source}"
        return result

    # Check Docker availability
    docker = shutil.which("docker")

    if not docker:
        result["status"] = "ERROR"
        result["message"] = "Docker CLI not found."
        return result

    # Default test inputs
    if test_inputs is None:
        test_inputs = ["0\n", "-1\n", "1\n"]

    if (
        not isinstance(test_inputs, (list, tuple))
        or not test_inputs
        or not all(isinstance(item, str) for item in test_inputs)
    ):
        result["message"] = (
            "test_inputs must be a non-empty list of strings."
        )
        return result

    # Validate timeout
    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ):
        result["status"] = "CONFIG_ERROR"
        result["message"] = "timeout_seconds must be positive."
        return result

    # Validate memory limit
    if (
        not isinstance(memory_limit_mb, (int, float))
        or isinstance(memory_limit_mb, bool)
        or memory_limit_mb <= 0
    ):
        result["status"] = "CONFIG_ERROR"
        result["message"] = "memory_limit_mb must be positive."
        return result

    try:
        # Create temporary workspace inside the project.
        # This location is accessible to Colima Docker.
        with tempfile.TemporaryDirectory(
            prefix="autograder_sanitizer_",
            dir=str(Path.cwd()),
        ) as build_directory:

            build_path = Path(build_directory)

            # Copy source file into Docker-accessible workspace.
            docker_source = build_path / source.name
            shutil.copy2(source, docker_source)

            # Compile using GCC with AddressSanitizer and UBSan.
            command = [
                docker,
                "run",
                "--rm",
                "--network=none",
                f"--memory={int(memory_limit_mb)}m",
                f"--memory-swap={int(memory_limit_mb)}m",
                "--cpus=1",
                "--pids-limit=64",
                "--mount",
                f"type=bind,source={build_path},target=/work",
                "-w",
                "/work",
                DOCKER_IMAGE,
                "gcc",
                "-g",
                "-O1",
                "-fsanitize=address,undefined",
                "-fno-omit-frame-pointer",
                source.name,
                "-o",
                "sanitized_program",
            ]

            compilation = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if compilation.returncode != 0:
                result["status"] = "COMPILE_ERROR"
                result["findings"].append(
                    compilation.stderr.strip()
                    or compilation.stdout.strip()
                    or "Sanitizer compilation failed."
                )
                return result

            executable = build_path / "sanitized_program"

            if not executable.is_file():
                result["status"] = "COMPILE_ERROR"
                result["message"] = (
                    "Sanitizer executable was not created."
                )
                return result

            # Execute every test input inside Docker.
            for test_input in test_inputs:

                execution = run_program(
                    str(executable),
                    test_input,
                    timeout_seconds,
                    memory_limit_mb=memory_limit_mb,
                )

                combined_output = (
                    execution.get("stdout", "")
                    + "\n"
                    + execution.get("stderr", "")
                )

                test = {
                    "input": test_input,
                    "status": "NOT_EVALUATED",
                    "return_code": execution.get("return_code"),
                    "stdout": execution.get("stdout", ""),
                    "stderr": execution.get("stderr", ""),
                }

                # Detect sanitizer errors.
                sanitizer_issue = (
                    "ERROR: AddressSanitizer" in combined_output
                    or "AddressSanitizer:DEADLYSIGNAL"
                    in combined_output
                    or "runtime error:" in combined_output
                    or "UndefinedBehaviorSanitizer"
                    in combined_output
                )

                if sanitizer_issue:
                    test["status"] = "ISSUE_DETECTED"

                    result["findings"].append({
                        "input": test_input,
                        "details": combined_output.strip(),
                    })

                elif execution.get("status") == "timeout":
                    test["status"] = "TIMEOUT"

                    result["findings"].append({
                        "input": test_input,
                        "details": (
                            f"Execution exceeded "
                            f"{timeout_seconds} seconds."
                        ),
                    })

                elif execution.get("status") != "completed":
                    test["status"] = "RUNTIME_ERROR"

                    result["findings"].append({
                        "input": test_input,
                        "details": (
                            combined_output.strip()
                            or "Program execution failed."
                        ),
                    })

                else:
                    test["status"] = "NO_ISSUE_DETECTED"

                result["tests"].append(test)

    except subprocess.TimeoutExpired:
        result["status"] = "ERROR"
        result["message"] = (
            "Sanitizer compilation exceeded 30 seconds."
        )
        return result

    except OSError as exc:
        result["status"] = "ERROR"
        result["message"] = str(exc)
        return result

    # Calculate final metric status.
    statuses = {
        test["status"] for test in result["tests"]
    }

    if "ISSUE_DETECTED" in statuses:
        result["score"] = 0
        result["status"] = "SANITIZER_ISSUE"

    elif "TIMEOUT" in statuses:
        result["score"] = None
        result["status"] = "TIMEOUT"

    elif "RUNTIME_ERROR" in statuses:
        result["score"] = None
        result["status"] = "RUNTIME_ERROR"

    else:
        result["score"] = 100
        result["status"] = "NO_ISSUE_DETECTED"

    result["message"] = (
        "ASan and UBSan were executed inside Docker. "
        "No sanitizer issue was detected in successful test runs. "
        "This does not prove the program is free of memory-safety bugs."
    )

    return result
