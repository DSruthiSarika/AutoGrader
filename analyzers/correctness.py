
import json

from agent.execution import run_program
from agent.test_generator import generate_edge_cases


def normalize_output(output):
    """Remove only leading and trailing whitespace."""
    return output.strip()


def load_test_cases(test_file):
    """Load instructor-provided test cases from an external JSON file."""
    with open(test_file, "r") as file:
        data = json.load(file)

    return data["tests"]


def check_correctness(
    executable,
    test_file,
    timeout_seconds,
    problem_config=None,
    memory_limit_mb=None,
    
):
    """
    Evaluate correctness using instructor-provided tests and
    optionally generated edge cases.
    """

    # 1. Load instructor-provided test cases.
    test_cases = load_test_cases(test_file)

    # Mark the origin of each test case.
    combined_tests = [
        {
            **test_case,
            "source": "instructor"
        }
        for test_case in test_cases
    ]

    # 2. Generate additional edge cases if a problem configuration exists.
    if problem_config is not None:
        generated_cases = generate_edge_cases(problem_config)

        for test_case in generated_cases:
            combined_tests.append({
                **test_case,
                "source": "generated"
            })

    # 3. Execute and evaluate every test case.
    results = []

    for test_case in combined_tests:
        input_data = test_case["input"]
        expected_output = test_case["expected_output"]

        result = run_program(
            executable,
            input_data,
            timeout_seconds,
            memory_limit_mb=memory_limit_mb,
        )

        actual_output = result["stdout"]

        passed = (
            result["status"] == "completed"
            and normalize_output(actual_output)
            == normalize_output(expected_output)
        )

        test_result = {
            "input": input_data,
            "expected_output": expected_output,
            "actual_output": actual_output,
            "status": result["status"],
            "passed": passed,
            "source": test_case["source"]
        }

        results.append(test_result)

    # 4. Calculate the correctness score.
    passed_count = sum(
        1 for result in results if result["passed"]
    )

    total_tests = len(results)

    score = (
        (passed_count / total_tests) * 100
        if total_tests > 0
        else 0
    )

    # 5. Identify the first failed test.
    first_failure = next(
        (result for result in results if not result["passed"]),
        None
    )

    return {
        "score": score,
        "passed_tests": passed_count,
        "total_tests": total_tests,
        "instructor_tests": len(test_cases),
        "generated_tests": (
            len(combined_tests) - len(test_cases)
        ),
        "results": results,
        "first_failure": first_failure
    }
