import json
import sys
from pathlib import Path

from agent.compiler import compile_c_program
from agent.execution import run_program
from analyzers.correctness import check_correctness
from analyzers.syntax import check_syntax
from analyzers.structure import check_structure
from analyzers.modularity import check_modularity
from analyzers.logical import check_logical
from analyzers.complexity import check_complexity
from analyzers.memory_safety import check_memory_safety
from analyzers.readability import check_readability
from analyzers.originality import check_originality


PROJECT_ROOT = Path(__file__).resolve().parent
SUBMISSIONS_DIR = PROJECT_ROOT / "submissions"

METRICS = (
    "correctness",
    "syntax",
    "structure",
    "modularity",
    "logical_behavior",
    "complexity",
    "memory_safety",
    "readability",
    "originality",
)


def load_rules():
    rules_path = PROJECT_ROOT / "rules" / "rules.json"
    with rules_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_problem_config(rules, source):
    """Load a matching problem configuration or use the default."""

    problem_configs = rules.get("problem_configs", {})
    problem_name = source.stem.lower()

    config_path = problem_configs.get(problem_name)

    if config_path is None:
        config_path = rules.get("default_problem_config")

        if config_path is None:
            raise ValueError(
                f"No configuration found for {source.name}"
            )
    else:
        pass

    config_path = PROJECT_ROOT / config_path

    with config_path.open("r", encoding="utf-8") as file:
        return json.load(file)
def get_submissions(args):
    if len(args) == 1 and args[0] == "--all":
        return sorted(SUBMISSIONS_DIR.glob("*.c"))

    if len(args) == 1:
        source = Path(args[0])

        if not source.is_absolute():
            source = PROJECT_ROOT / source

        if source.is_file() and source.suffix.lower() == ".c":
            return [source]

        raise ValueError(f"Invalid C source file: {source}")

    raise ValueError(
        "Usage:\n"
        "  python main.py <submission.c>\n"
        "  python main.py --all"
    )


def load_test_cases(test_file):
    with test_file.open("r", encoding="utf-8") as file:
        data = json.load(file)

    tests = data.get("tests", [])

    if not tests:
        raise ValueError(
            "No test cases found in the correctness test file."
        )

    for test in tests:
        if "input" not in test or "expected_output" not in test:
            raise ValueError(
                "Every test case must contain input and expected_output."
            )

    return tests


def safe_analyze(metric_name, function, *args, **kwargs):
    try:
        result = function(*args, **kwargs)

        if not isinstance(result, dict):
            raise TypeError("Analyzer did not return a dictionary.")

        return result

    except Exception as exc:
        return {
            "metric": metric_name,
            "score": None,
            "status": "ERROR",
            "message": str(exc),
            "findings": [],
        }


def valid_score(score):
    return (
        isinstance(score, (int, float))
        and not isinstance(score, bool)
        and 0 <= score <= 100
    )



def print_metric(name, result, weight):
    score = result.get("score")
    status = result.get("status", "UNKNOWN")

    if valid_score(score):
        print(
            f"{name:<22} {score:6.2f}/100"
            f"  Weight: {weight:>2}%  [{status}]"
        )
    else:
        print(
            f"{name:<22} {'N/A':>9}"
            f"  Weight: {weight:>2}%  [{status}]"
        )

    # Display concise complexity analysis details.
    if name.lower() == "complexity":
        detected = result.get("estimated_complexity") or "N/A"
        expected = result.get("expected_complexity") or "N/A"
        confidence = result.get("confidence") or "N/A"

        static = result.get("static_analysis", {}).get(
            "estimated_complexity"
        )
        runtime = result.get("runtime_analysis", {}).get(
            "estimated_complexity"
        )

        assessment = result.get("assessment")

        if assessment == "AGREE":
            analysis_status = "AGREEMENT"
        elif assessment == "STATIC_ONLY":
            analysis_status = "STATIC ANALYSIS"
        elif assessment == "RUNTIME_ONLY":
            analysis_status = "RUNTIME ANALYSIS"
        else:
            analysis_status = "DISAGREEMENT"

        print(f"  Detected complexity:  {detected}")
        print(f"  Expected complexity:  {expected}")
        print(f"  Confidence:           {confidence}")
        print(f"  Analysis status:      {analysis_status}")

    else:
        message = result.get("message")
        if message:
            print(f"  Note: {message}")


def calculate_weighted_grade(results, weights, total_marks=100):
    """
    Return a full grade if all metrics are available.
    Otherwise, return a provisional grade normalized against
    the total weight of metrics with valid scores.
    """
    weighted_total = 0.0
    available_weight = 0.0
    missing_metrics = []
    available_metrics = []

    for metric in METRICS:
        result = results.get(metric, {})
        score = result.get("score")
        weight = weights.get(metric, 0)

        if valid_score(score):
            weighted_total += score * weight / 100
            available_weight += weight
            available_metrics.append(metric)
        else:
            missing_metrics.append(metric)

    if available_weight == 0:
        return {
            "available": False,
            "provisional": False,
            "score": None,
            "final_marks": None,
            "available_weight": 0,
            "missing_metrics": missing_metrics,
            "available_metrics": available_metrics,
        }

    normalized_score = weighted_total * 100 / available_weight
    final_marks = normalized_score * total_marks / 100

    return {
        "available": True,
        "provisional": bool(missing_metrics),
        "score": normalized_score,
        "final_marks": final_marks,
        "available_weight": available_weight,
        "missing_metrics": missing_metrics,
        "available_metrics": available_metrics,
    }


def _grade_submission_impl(
    source,
    rules,
    all_sources,
    test_cases,
    problem_config,
    executable_tracker=None
):
    print("\n" + "=" * 65)
    print(f"Submission: {source.name}")
    print("=" * 65)

    weights = rules["grading"]["weights"]
    timeout = rules["execution"]["timeout_seconds"]
    memory_limit = rules["execution"].get("memory_limit_mb", 128)
    syntax_rules = rules["syntax"]
    test_file = PROJECT_ROOT / problem_config["correctness"]["test_file"]
    total_marks = rules["grading"].get("total_marks", 100)

    test_inputs = [
        str(test["input"])
        for test in test_cases
    ]
    expected_outputs = [
        str(test["expected_output"])
        for test in test_cases
    ]

    results = {}

    # Compile the source once for the correctness runner.
    compilation = safe_analyze(
        "compilation",
        compile_c_program,
        str(source),
    )

    executable = compilation.get("executable")
    compiled = bool(compilation.get("success") and executable)
    if executable_tracker is not None:
        executable_tracker["path"] = executable

    smoke_ok = False
    smoke_result = None
    smoke_status = None

    if not compiled:
        error = (
            compilation.get("error")
            or compilation.get("message")
            or "Compilation failed."
        )
        print(f"\nCompilation failed:\n{error}")
    else:
        # First-pass smoke test required by the assignment. This uses the
        # first configured test input and the configured wall-clock timeout.
        print("\nFirst-pass smoke test")
        smoke_result = safe_analyze(
            "smoke_test",
            run_program,
            executable,
            str(test_cases[0]["input"]) ,
            timeout,
            memory_limit_mb=memory_limit,
        )
        smoke_status = smoke_result.get("status")
        smoke_ok = (
            smoke_status == "completed"
            and smoke_result.get("return_code") == 0
        )
        
        if smoke_ok:
            print("Smoke test: PASS")
        else:
            print(
                "Smoke test: FAIL - "
                + str(smoke_result.get("stderr") or smoke_result.get("status"))
            )
            if smoke_status == "timeout":
                print(
                    "Execution-based analyzers will be skipped because "
                    "the program exceeded the time limit."
                )

            elif smoke_status == "output_limit_exceeded":
                print(
                    "Execution-based analyzers will be skipped because "
                    "the program exceeded the output size limit."
                )

            elif smoke_status == "runtime_error":
                print(
                "Execution-based analyzers will be skipped because "
                "the program terminated with a runtime error."
            )

            else:
                print(
                    "Execution-based analyzers will be skipped because "
                    "the smoke test did not complete successfully."
            )

    execution_allowed = compiled and smoke_ok

    # 1. Correctness
    print("\n[1/9] Correctness")

    if execution_allowed:
        
            correctness = safe_analyze(
                "correctness",
                check_correctness,
                executable,
                str(test_file),
                timeout,
                problem_config=problem_config,
                memory_limit_mb=memory_limit,
            )

            score = correctness.get("score")
            if valid_score(score):
                if score == 100:
                    correctness["status"] = "PASS"
                elif score == 0:
                    correctness["status"] = "FAIL"
                else:
                    correctness["status"] = "REVIEW"

            results["correctness"] = correctness

       
    else:
        results["correctness"] = {
            "score": None,
            "status": ("NOT_EVALUATED_COMPILE_ERROR" if not compiled else "SKIPPED_SMOKE_TEST"),
            "message": (
                "Correctness tests could not run because compilation failed."
                if not compiled else "Correctness tests were skipped because the smoke test failed or timed out."
            ),
        }

    print_metric(
        "Correctness",
        results["correctness"],
        weights["correctness"],
    )

    failure = results["correctness"].get("first_failure")
    if failure:
        print("  First failing test:")
        print(f"    Input:    {failure.get('input', '')!r}")
        print(f"    Expected: {failure.get('expected_output', '')!r}")
        print(f"    Actual:   {failure.get('actual_output', '')!r}")
        print(f"    Status:   {failure.get('status', 'unknown')}")

    # 2. Syntax
    print("\n[2/9] Syntax")

    if syntax_rules.get("enabled", True):
        results["syntax"] = safe_analyze(
            "syntax",
            check_syntax,
            str(source),
            compiler=syntax_rules["compiler"],
            standard=syntax_rules["standard"],
            flags=syntax_rules["flags"],
        )
    else:
        results["syntax"] = {
            "score": None,
            "status": "DISABLED",
            "message": "Syntax checking is disabled in rules.json.",
        }

    print_metric("Syntax", results["syntax"], weights["syntax"])

    # 3. Structure
    print("\n[3/9] Structure")

    results["structure"] = safe_analyze(
        "structure",
        check_structure,
        str(source),
    )

    print_metric(
        "Structure",
        results["structure"],
        weights["structure"],
    )

    # 4. Modularity
    print("\n[4/9] Modularity")

    results["modularity"] = safe_analyze(
        "modularity",
        check_modularity,
        str(source),
        problem_config
    )

    print_metric(
        "Modularity",
        results["modularity"],
        weights["modularity"],
    )

    # 5. Logical behavior
    print("\n[5/9] Logical behavior")

    logical_rules = problem_config.get("logical_behavior", {})

    if not logical_rules.get("enabled", True):
        results["logical_behavior"] = {
            "score": None,
            "status": "NOT_EVALUATED",
            "message": logical_rules.get(
                "reason",
                "Logical behavior evaluation is disabled for this problem."
            ),
        }

    elif execution_allowed:
        results["logical_behavior"] = safe_analyze(
            "logical_behavior",
            check_logical,
            str(source),
            test_inputs=test_inputs,
            expected_outputs=expected_outputs,
            logical_config=logical_rules,
            timeout_seconds=timeout,
            executable_path=executable,
            memory_limit_mb=memory_limit,
            
        )

        score = results["logical_behavior"].get("score")

        if valid_score(score):
            if score == 100:
                results["logical_behavior"]["status"] = "PASS"
            elif score == 0:
                results["logical_behavior"]["status"] = "FAIL"
            else:
                results["logical_behavior"]["status"] = "REVIEW"

    else:
        results["logical_behavior"] = {
            "score": None,
            "status": (
                "NOT_EVALUATED_COMPILE_ERROR"
                if not compiled
                else "SKIPPED_SMOKE_TEST"
            ),
            "message": (
                "Logical behavior could not be tested because compilation failed."
                if not compiled
                else "Logical tests were skipped because the smoke test failed or timed out."
            ),
        }

    print_metric(
        "Logical behavior",
        results["logical_behavior"],
        weights["logical_behavior"],
    )

    # 6. Complexity
    print("\n[6/9] Complexity")

    complexity_config = problem_config.get("complexity", {})

    if not complexity_config.get("enabled", True):
        results["complexity"] = {
            "score": None,
            "status": "NOT_EVALUATED",
            "message": complexity_config.get(
            "reason",
            "Complexity benchmarking is disabled for this problem."
        ),
    }

    elif execution_allowed:
        results["complexity"] = safe_analyze(
            "complexity",
            check_complexity,
            str(source),
            timeout_seconds=timeout,
            test_inputs=test_inputs,
            executable_path=executable,
            repetitions=complexity_config.get("repetitions", 5),
            benchmark_cases=complexity_config.get("benchmark_cases"),
            expected_complexity=complexity_config.get("required"),
        )

        if valid_score(results["complexity"].get("score")):
            existing_message = results["complexity"].get("message", "")
            results["complexity"]["message"] = (
                existing_message
                + " Runtime-efficiency heuristic only; "
                "not a formal Big-O result."
            ).strip()

    else:
        results["complexity"] = {
            "score": None,
            "status": (
                "NOT_EVALUATED_COMPILE_ERROR"
                if not compiled else "SKIPPED_SMOKE_TEST"
            ),
            "message": (
                "Runtime efficiency could not be measured because "
                "the program failed to compile."
                if not compiled else
                "Complexity measurement was skipped because "
                "the smoke test failed or timed out."
            ),
        }
    print_metric(
        "Complexity",
        results["complexity"],
        weights["complexity"],
    )

    # 7. Memory safety
    print("\n[7/9] Memory safety")

    if execution_allowed:
        results["memory_safety"] = safe_analyze(
            "memory_safety",
            check_memory_safety,
            str(source),
            test_inputs=test_inputs,
            timeout_seconds=timeout,
            memory_limit_mb=memory_limit,
        )

        memory_result = results["memory_safety"]
        memory_status = memory_result.get("status", "")

        # An inconclusive run is not evidence of a memory defect.
        if memory_status in {
            "TIMEOUT",
            "ERROR",
            "COMPILE_ERROR",
            "NOT_EVALUATED",
            "RUNTIME_ERROR",
        }:
            memory_result["score"] = None

            if memory_status in {
                "ERROR",
                "COMPILE_ERROR",
                "NOT_EVALUATED",
            }:
                memory_result["status"] = "NOT_EVALUATED"

            memory_result["message"] = (
                "Memory safety could not be fully evaluated. "
                "A timeout or ordinary runtime error is not, by itself, "
                "proof of a memory-safety defect."
            )

        elif memory_status in {
            "SANITIZER_ISSUE",
            "MEMORY_ERROR",
            "ISSUE_DETECTED",
        }:
            memory_result["score"] = 0
            memory_result["status"] = "SANITIZER_ISSUE"
            memory_result["message"] = (
                "A sanitizer issue was reported. Review the analyzer "
                "findings for details."
            )

        elif memory_status == "NO_ISSUE_DETECTED":
            memory_result["score"] = 100
            memory_result["status"] = "PASS"
            memory_result["message"] = (
                "AddressSanitizer (ASan): No issues detected. "
                "UndefinedBehaviorSanitizer (UBSan): No issues detected."
            )

        else:
            memory_result["score"] = None
            memory_result["status"] = "NOT_EVALUATED"
            memory_result["message"] = (
                "The analyzer returned an unrecognized status; "
                "this metric was not scored."
            )

    else:
        results["memory_safety"] = {
            "score": None,
            "status": ("NOT_EVALUATED_COMPILE_ERROR" if not compiled else "SKIPPED_SMOKE_TEST"),
            "message": (
                "Memory safety could not be evaluated because the program failed to compile."
                if not compiled else "Memory-safety testing was skipped because the smoke test failed or timed out."
            ),
        }

    print_metric(
        "Memory safety",
        results["memory_safety"],
        weights["memory_safety"],
    )

    # 8. Readability
    print("\n[8/9] Readability")

    results["readability"] = safe_analyze(
        "readability",
        check_readability,
        str(source),
    )

    if valid_score(results["readability"].get("score")):
        results["readability"]["message"] = (
            "Heuristic readability estimate. Review findings manually."
        )

    print_metric(
        "Readability",
        results["readability"],
        weights["readability"],
    )

    # 9. Originality
    print("\n[9/9] Originality")

    originality_rules = rules.get("originality", {})

    if originality_rules.get("enabled", True):

        configured_files = originality_rules.get(
            "comparison_files", []
        )

        comparison_files = [
            str((SUBMISSIONS_DIR / filename).resolve())
            for filename in configured_files
            if isinstance(filename, str) and filename.strip()
        ]

        results["originality"] = safe_analyze(
            "originality",
            check_originality,
            str(source),
            comparison_files=comparison_files,
            threshold=originality_rules.get("threshold", 0.85),
        )

    else:
        results["originality"] = {
            "metric": "originality",
            "score": None,
            "status": "NOT_EVALUATED",
            "comparisons": [],
            "findings": [],
            "message": "Originality analysis is disabled in instructor rules.",
        }

    if valid_score(results["originality"].get("score")):
        results["originality"]["message"] = (
            "Token-based dissimilarity estimate only. "
            "It is not proof of originality or plagiarism."
        )

    print_metric(
        "Originality estimate",
        results["originality"],
        weights["originality"],
    )
    # Weighted grade
    print("\n" + "-" * 65)
    print("WEIGHTED GRADE")
    print("-" * 65)

    grade = calculate_weighted_grade(
        results,
        weights,
        total_marks,
    )

    if not compiled:
        print("Grade: NOT AVAILABLE - compilation failed.")
        print("Static-analysis results are shown above, but no grade is assigned.")
    elif not smoke_ok:
        print("Grade: NOT AVAILABLE - first-pass smoke test failed or timed out.")
        print("A partial report is provided; execution-dependent metrics were skipped.")
    elif not grade["available"]:
        print("Grade: NOT AVAILABLE")
        print("No metrics had valid scores.")

    elif grade["provisional"]:
        print(
            f"Provisional weighted score: "
            f"{grade['score']:.2f}/100"
        )
        print(
            f"Provisional marks: "
            f"{grade['final_marks']:.2f}/{total_marks}"
        )
        print(
            f"Evaluated weight: "
            f"{grade['available_weight']:.0f}% of total"
        )
        print(
            "Metrics not evaluated: "
            + ", ".join(grade["missing_metrics"])
        )
        print(
            "WARNING: This is a provisional grade, "
            "not a complete assessment."
        )

    else:
        print(f"Weighted score: {grade['score']:.2f}/100")
        print(
            f"Final marks: {grade['final_marks']:.2f}/{total_marks}"
        )


    results["_submission_status"] = {
        "compiled": compiled,
        "smoke_test_passed": (
            smoke_ok if compiled else None
        ),
        "smoke_status": (smoke_result or {}).get("status") if smoke_result else None,
    }

    return results

def grade_submission(
    source,
    rules,
    all_sources,
    test_cases,
    problem_config
):
    """Grade a submission and always clean up its temporary executable."""

    executable_tracker = {"path": None}

    try:
        return _grade_submission_impl(
            source,
            rules,
            all_sources,
            test_cases,
            problem_config,
            executable_tracker
        )

    finally:
        executable = executable_tracker.get("path")

        if executable:
            Path(executable).unlink(missing_ok=True)
def generate_reports(all_results, weights, total_marks):
    """
    Generate JSON and text reports for all graded submissions.
    """

    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_data = {
        "total_submissions": len(all_results),
        "total_marks": total_marks,
        "metric_weights": weights,
        "submissions": {}
    }

    text_lines = [
        "=" * 70,
        "                         AUTO GRADER REPORT",
        "=" * 70,
        f"Total submissions: {len(all_results)}",
        f"Total marks: {total_marks}",
        "",
    ]

    for filename, results in all_results.items():

        submission_status = results.get(
            "_submission_status", {}
        )

        grade = calculate_weighted_grade(
            results,
            weights,
            total_marks
        )

        compiled = submission_status.get("compiled", False)
        smoke_passed = submission_status.get(
            "smoke_test_passed", False
        )

        if not compiled:
            grade_status = "COMPILATION_FAILED"
            grade_text = "NOT AVAILABLE"

        elif not smoke_passed:
            grade_status = "SMOKE_TEST_FAILED"
            grade_text = "NOT AVAILABLE"

        elif not grade["available"]:
            grade_status = "NOT_AVAILABLE"
            grade_text = "NOT AVAILABLE"

        elif grade["provisional"]:
            grade_status = "PROVISIONAL"
            grade_text = (
                f"{grade['final_marks']:.2f}/{total_marks}"
            )

        else:
            grade_status = "FINAL"
            grade_text = (
                f"{grade['final_marks']:.2f}/{total_marks}"
            )

        metric_data = {}

        text_lines.extend([
            "-" * 70,
            f"Submission: {filename}",
            "-" * 70,
            f"Compilation successful: {compiled}",
            (
                f"Smoke test passed: "
                f"{smoke_passed if compiled else 'NOT RUN'}"
            ),
            ""
     ])

        for metric in METRICS:
            metric_result = results.get(metric, {})

            metric_data[metric] = metric_result.copy()

            score = metric_result.get("score")
            status = metric_result.get("status", "UNKNOWN")

            score_text = (
                f"{score:.2f}/100"
                if valid_score(score)
                else "N/A"
            )

            text_lines.append(
                f"{metric}: {score_text} | Status: {status}"
            )

        report_data["submissions"][filename] = {
            "execution": submission_status,
            "metrics": metric_data,
            "grade": {
                "status": grade_status,

                "score": (
                    round(grade["score"], 2)
                    if grade_status in ("FINAL", "PROVISIONAL")
                    else None
                ),

                "final_marks": (
                    round(grade["final_marks"], 2)
                    if grade_status in ("FINAL", "PROVISIONAL")
                    else None
                ),

                "available_weight": round(
                    grade.get("available_weight", 0), 2
                ),

                "missing_metrics": grade.get("missing_metrics", [])
            }
        }

        text_lines.extend([
            "",
            f"Grade status: {grade_status}",
            f"Grade: {grade_text}",
            ""
        ])

    text_lines.extend([
        "=" * 70,
        "                       END OF REPORT",
        "=" * 70
    ])

    json_path = reports_dir / "grading_report.json"
    text_path = reports_dir / "grading_report.txt"

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(report_data, file, indent=4, default=str)

    with text_path.open("w", encoding="utf-8") as file:
        file.write("\n".join(text_lines) + "\n")
        
    return json_path, text_path


def main():
    try:
        submissions = get_submissions(sys.argv[1:])
        rules = load_rules()
        weights = rules["grading"]["weights"]

        # Validate grading weights.
        if set(weights) != set(METRICS):
            raise ValueError(
                "The grading weights must contain exactly "
                "the nine configured metric names."
            )

        if any(
            not isinstance(weight, (int, float))
            or isinstance(weight, bool)
            or weight < 0
            for weight in weights.values()
        ):
            raise ValueError(
                "Metric weights must be non-negative numbers."
            )

        if sum(weights.values()) != 100:
            raise ValueError(
                "Metric weights must add up to 100."
            )

    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"Configuration error: {exc}")
        return 1

    if not submissions:
        print(f"No .c files found in {SUBMISSIONS_DIR}")
        return 1

    print("=" * 65)
    print("                         AUTO GRADER")
    print("=" * 65)
    print(f"Submissions selected: {len(submissions)}")
    print(f"Total grading weight: {sum(weights.values())}%")

    all_results = {}

    # Grade each submission independently.
    for index, source in enumerate(submissions, start=1):
        print(f"\nProcessing submission {index}/{len(submissions)}")

        try:
            # Select the matching problem configuration.
            problem_config = load_problem_config(rules, source)

            

            # Load problem-specific correctness tests.
            correctness_config = problem_config.get("correctness", {})
            test_file = correctness_config.get("test_file")

            if not test_file:
                raise ValueError(
                    f"Correctness test file not configured for {source.name}"
                )

            test_cases = load_test_cases(
                PROJECT_ROOT / test_file
            )

            # Grade the submission.
            all_results[source.name] = grade_submission(
                source,
                rules,
                submissions,
                test_cases,
                problem_config
            )

        except Exception as exc:
            print(f"Could not grade {source.name}: {exc}")
            print("Continuing to the next submission.")

    # Batch summary.
    print("\n" + "=" * 65)
    print("BATCH SUMMARY")
    print("=" * 65)

    for filename, results in all_results.items():
        available = sum(
            1
            for metric in METRICS
            if valid_score(
                results.get(metric, {}).get("score")
            )
        )

        grade_info = calculate_weighted_grade(results, weights)
        grade = grade_info.get("score")

        # A final grade is unavailable when execution-dependent
        # grading was blocked by compilation/smoke-test failure.
        blocked_statuses = {
            "NOT_EVALUATED_COMPILE_ERROR",
            "SKIPPED_SMOKE_TEST",
        }

        execution_blocked = any(
            results.get(metric, {}).get("status") in blocked_statuses
            for metric in (
                "correctness",
                "logical",
                "complexity",
                "memory_safety",
            )
        )

        if grade is not None and not execution_blocked:
            print(
                f"{filename}: {available}/9 metrics scored | "
                f"Grade: {grade:.2f}/100"
            )
        else:
            print(
                f"{filename}: {available}/9 metrics scored | "
                "Grade: NOT AVAILABLE"
            )

    # Generate reports for all processed submissions.
    json_path, text_path = generate_reports(
        all_results,
        weights,
        rules["grading"].get("total_marks", 100)
    )

    print("\n" + "=" * 65)
    print("REPORT GENERATION")
    print("=" * 65)
    print(f"JSON report: {json_path}")
    print(f"Text report: {text_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

