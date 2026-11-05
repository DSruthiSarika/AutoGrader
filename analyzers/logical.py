
"""
Configuration-driven edge-case evaluator for compiled C programs.

Each configured case supplies:
    name: descriptive case name
    input: exact stdin text
    expected_output: expected stdout text

The analyzer compares normalized stdout with the instructor-provided
expected output. It does not infer expected behavior automatically.
"""

import subprocess
import tempfile
from pathlib import Path

from agent.execution import run_program

MAX_CASES = 200


def _normalize_output(value):
    """Normalize line endings and ignore surrounding whitespace."""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def _compile_if_needed(source_file, executable_path):
    """Return executable path, temporary directory, and compile error."""
    if executable_path is not None:
        executable = Path(executable_path)
        if not executable.is_file():
            return None, None, f"Compiled executable not found: {executable}"
        return executable, None, None

    if source_file is None:
        return None, None, "A source file or compiled executable is required."

    source = Path(source_file)
    if not source.is_file():
        return None, None, f"Source file not found: {source}"

    temp_dir = tempfile.TemporaryDirectory(
        prefix="autograder_edge_cases_"
    )
    executable = Path(temp_dir.name) / "edge_case_program"

    try:
        compilation = subprocess.run(
            [
                "gcc",
                str(source.resolve()),
                "-std=c11",
                "-O0",
                "-o",
                str(executable)
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        temp_dir.cleanup()
        return None, None, f"Compilation could not complete: {exc}"

    if compilation.returncode != 0:
        message = compilation.stderr.strip() or "GCC compilation failed."
        temp_dir.cleanup()
        return None, None, message

    return executable, temp_dir, None


def _validate_config(config):
    """Validate the instructor-defined edge-case configuration."""
    if not isinstance(config, dict):
        raise ValueError("edge-case configuration must be a JSON object.")

    if config.get("enabled", True) is not True:
        return []

    cases = config.get("cases")

    if not isinstance(cases, list) or not cases:
        raise ValueError(
            "Edge-case evaluation is enabled, but "
            "'cases' must be a non-empty list."
        )

    if len(cases) > MAX_CASES:
        raise ValueError(
            f"At most {MAX_CASES} edge cases may be configured."
        )

    validated = []

    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(
                f"Edge case {index} must be a JSON object."
            )

        name = case.get("name", f"edge_case_{index}")
        input_data = case.get("input")
        expected_output = case.get("expected_output")

        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"Edge case {index} requires a non-empty name."
            )

        if not isinstance(input_data, str):
            raise ValueError(
                f"Input for edge case '{name}' must be a string."
            )

        if not isinstance(expected_output, str):
            raise ValueError(
                f"expected_output for edge case '{name}' must be a string."
            )

        validated.append({
            "name": name,
            "input": input_data,
            "expected_output": expected_output
        })

    return validated


def check_logical(
    source_file=None,
    test_inputs=None,
    expected_outputs=None,
    timeout_seconds=3,
    executable_path=None,
    logical_config=None,
    output_limit_mb=5,
    memory_limit_mb=None,
):
    """
    Run instructor-configured edge cases against a compiled C program.

    test_inputs and expected_outputs are retained for compatibility
    with older callers, but are deliberately not reused.

    Logical edge cases must be configured separately from correctness tests.
    """

    result = {
        "metric": "logical_behavior",
        "source_file": (
            str(source_file) if source_file is not None else None
        ),
        "score": None,
        "status": "NOT_EVALUATED",
        "passed_checks": 0,
        "total_checks": 0,
        "checks": [],
        "findings": []
    }

    if logical_config is None:
        result["message"] = (
            "No separate logical edge cases were configured. "
            "Correctness tests are not reused."
        )
        return result

    if not isinstance(logical_config, dict):
        result["status"] = "CONFIG_ERROR"
        result["message"] = "logical_config must be a JSON object."
        return result

    if logical_config.get("enabled", True) is False:
        result["message"] = logical_config.get(
            "reason",
            "Logical edge-case evaluation is disabled."
        )
        return result

    try:
        cases = _validate_config(logical_config)

    except ValueError as exc:
        result["status"] = "CONFIG_ERROR"
        result["message"] = str(exc)
        result["findings"].append(str(exc))
        return result

    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ):
        result["status"] = "CONFIG_ERROR"
        result["message"] = (
            "timeout_seconds must be a positive number."
        )
        return result

    executable, owned_temp_dir, compile_error = _compile_if_needed(
        source_file,
        executable_path
    )

    if compile_error:
        result["status"] = "COMPILE_ERROR"
        result["message"] = compile_error
        result["findings"].append(compile_error)
        return result

    try:
        for case in cases:

            run = run_program(
                executable,
                case["input"],
                timeout_seconds,
                memory_limit_mb=memory_limit_mb,
                output_limit_mb=output_limit_mb
            )

            actual_output = run.get("stdout", "")

            execution_ok = (
                run.get("status") == "completed"
                and run.get("return_code") == 0
            )

            output_matches = (
                _normalize_output(actual_output)
                == _normalize_output(case["expected_output"])
            )

            passed = execution_ok and output_matches

            check = {
                "name": case["name"],
                "input": case["input"],
                "expected_output": case["expected_output"],
                "actual_output": actual_output,
                "execution_status": run.get("status"),
                "return_code": run.get("return_code"),
                "stderr": run.get("stderr", ""),
                "status": "PASS" if passed else "FAIL",
                "passed": passed
            }

            if not passed:

                if not execution_ok:
                    check["message"] = (
                        "The program did not complete successfully "
                        "(possible timeout, runtime error, "
                        "or output-limit violation)."
                    )
                else:
                    check["message"] = (
                        "Actual output did not match expected output."
                    )

                result["findings"].append({
                    "name": case["name"],
                    "input": case["input"],
                    "expected_output": case["expected_output"],
                    "actual_output": actual_output,
                    "execution_status": run.get("status"),
                    "return_code": run.get("return_code"),
                    "message": check["message"]
                })

            result["checks"].append(check)

    finally:
        if owned_temp_dir is not None:
            owned_temp_dir.cleanup()

    total = len(result["checks"])

    passed = sum(
        check["passed"] for check in result["checks"]
    )

    result["total_checks"] = total
    result["passed_checks"] = passed

    result["score"] = (
        round(100 * passed / total, 2) if total else None
    )

    result["status"] = (
        "PASS" if result["score"] == 100
        else "FAIL" if result["score"] == 0
        else "REVIEW"
    )

    result["message"] = (
        f"{passed}/{total} configured logical edge cases passed."
    )

    return result
