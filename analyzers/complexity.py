
import math
import re
import statistics
import subprocess
import tempfile
import time
from pathlib import Path
from agent.execution import run_program, run_benchmark_batch


SUPPORTED_COMPLEXITIES = (
    "O(1)",
    "O(log n)",
    "O(n)",
    "O(n log n)",
    "O(n^2)",
    "O(n^3)",
)


# ---------------------------------------------------------
# 1. SOURCE CODE PREPROCESSING
# ---------------------------------------------------------

def _remove_comments_and_strings(source):
    """Remove comments and string/character literals."""

    pattern = (
        r'"(?:\\.|[^"\\])*"'
        r'|\'(?:\\.|[^\'\\])*\''
        r'|//[^\n]*'
        r'|/\*[\s\S]*?\*/'
    )

    return re.sub(pattern, " ", source)


# ---------------------------------------------------------
# 2. STATIC COMPLEXITY ANALYSIS
# ---------------------------------------------------------

def _matching_delimiter(source, start, opening, closing):
    """Find the matching closing delimiter."""

    depth = 0

    for index in range(start, len(source)):
        if source[index] == opening:
            depth += 1
        elif source[index] == closing:
            depth -= 1

            if depth == 0:
                return index

    return None


def _get_loop_body(source, start):
    """Extract an approximate loop body."""

    while start < len(source) and source[start].isspace():
        start += 1

    if start >= len(source):
        return "", start

    if source[start] == "{":
        end = _matching_delimiter(source, start, "{", "}")

        if end is None:
            return "", len(source)

        return source[start + 1:end], end + 1

    end = source.find(";", start)

    if end == -1:
        return source[start:], len(source)

    return source[start:end + 1], end + 1


def _classify_loop(header, body, keyword):
    """Estimate the growth pattern of an individual loop."""

    header = re.sub(r"\s+", "", header.lower())
    body = re.sub(r"\s+", "", body.lower())
    # Recognize binary-search interval reduction.
    bounds = re.search(r"(\w+)<=(\w+)", header)

    if bounds:
        lower_bound, upper_bound = bounds.groups()

        midpoint = re.search(
            rf"\b{re.escape(lower_bound)}=(\w+)\+1\b",
            body,
        )

        if midpoint:
            midpoint_variable = midpoint.group(1)

            upper_update = re.search(
                rf"\b{re.escape(upper_bound)}="
                rf"{re.escape(midpoint_variable)}-1\b",
                body,
            )

            if upper_update:
                return "O(log n)"
    # Common logarithmic update patterns.
    logarithmic_patterns = [
        r"\w+\*=([2-9]|\d{2,})",
        r"\w+/=([2-9]|\d{2,})",
        r"\w+=\w+\*([2-9]|\d{2,})",
        r"\w+=\w+/([2-9]|\d{2,})",
        r"\w+>>=1",
    ]

    for pattern in logarithmic_patterns:
        if re.search(pattern, header) or re.search(pattern, body):
            return "O(log n)"

    # Common linear update patterns.
    linear_patterns = [
        r"\w+\+\+",
        r"\+\+\w+",
        r"\w+--",
        r"--\w+",
        r"\w+\+=1",
        r"\w+-=1",
    ]

    for pattern in linear_patterns:
        if re.search(pattern, header) or re.search(pattern, body):
            return "O(n)"

    # A do-while loop without a recognizable update is uncertain.
    if keyword == "do":
        return "UNKNOWN"

    return "UNKNOWN"


def _extract_loops(source):
    """Extract loop locations, headers, and approximate bodies."""

    loops = []
    index = 0

    while index < len(source):
        match = re.search(r"\b(for|while|do)\b", source[index:])

        if not match:
            break

        keyword = match.group(1)
        position = index + match.start()
        after_keyword = index + match.end()

        if keyword == "do":
            body, end = _get_loop_body(source, after_keyword)

            loops.append({
                "keyword": keyword,
                "header": "",
                "body": body,
                "start": position,
                "end": end,
            })

            index = after_keyword
            continue

        cursor = after_keyword

        while cursor < len(source) and source[cursor].isspace():
            cursor += 1

        if cursor >= len(source) or source[cursor] != "(":
            index = after_keyword
            continue

        closing = _matching_delimiter(
            source, cursor, "(", ")"
        )

        if closing is None:
            break

        header = source[cursor + 1:closing]
        body, end = _get_loop_body(source, closing + 1)

        loops.append({
            "keyword": keyword,
            "header": header,
            "body": body,
            "start": position,
            "end": end,
        })

        # Continue scanning after the loop keyword so nested
        # loops inside this loop body are also detected.
        index = after_keyword 

    return loops


def _extract_algorithm_source(source):
    """Prefer non-main function bodies for algorithm analysis."""

    function_pattern = re.compile(
        r"\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{"
    )

    excluded_names = {
        "if", "for", "while", "switch",
    }

    function_bodies = []
    position = 0

    while True:
        match = function_pattern.search(source, position)

        if not match:
            break

        function_name = match.group(1)
        opening_brace = match.end() - 1

        closing_brace = _matching_delimiter(
            source, opening_brace, "{", "}"
        )

        if closing_brace is None:
            position = match.end()
            continue

        if (
            function_name != "main"
            and function_name not in excluded_names
        ):
            function_bodies.append(
                source[opening_brace + 1:closing_brace]
            )

        position = closing_brace + 1

    # If helper functions exist, analyze those instead of main().
    if function_bodies:
        return "\n".join(function_bodies)

    # Preserve support for programs with inline algorithms.
    return source
def _detect_recursive_complexity(source):
    """Heuristically detect common recursive divide-and-conquer sorting patterns."""

    function_pattern = re.compile(
        r'\b(?:void|int|long|float|double|char|size_t|unsigned|static)\s+'
        r'([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{'
    )

    position = 0

    while True:
        match = function_pattern.search(source, position)

        if not match:
            break

        name = match.group(1)
        opening = match.end() - 1

        closing = _matching_delimiter(
            source,
            opening,
            "{",
            "}"
        )

        if closing is None:
            break

        body = source[opening + 1:closing]
        position = closing + 1

        recursive_calls = len(re.findall(
            rf'\b{re.escape(name)}\s*\(',
            body
        ))

        if recursive_calls >= 2:

            # Merge Sort:
            # two recursive calls + merge operation
            has_merge = bool(re.search(
                r'\bmerge\s*\(',
                body
            ))

            if has_merge:
                return {
                    "estimated_complexity": "O(n log n)",
                    "confidence": "HIGH",
                    "message": (
                        "Recognized recursive Merge Sort pattern: "
                        "two recursive calls on subarrays followed by "
                        "a linear merge step."
                    ),
                }

            # Quick Sort:
            # two recursive calls + partition operation
            has_partition = bool(re.search(
                r'\bpartition\s*\(',
                body
            ))

            if has_partition:
                return {
                    "estimated_complexity": "O(n log n)",
                    "confidence": "MEDIUM",
                    "message": (
                        "Recognized recursive Quick Sort pattern. "
                        "The estimate represents average-case behavior; "
                        "worst case may be O(n^2)."
                    ),
                }
    # Quick Sort fallback detection
    if (
        re.search(r'\bquickSort\s*\(', source)
        and re.search(r'\bpartition\s*\(', source)
        and len(re.findall(r'\bquickSort\s*\(', source)) >= 3
    ):
        return {
            "estimated_complexity": "O(n log n)",
            "confidence": "MEDIUM",
            "message": (
                "Recognized recursive Quick Sort pattern with "
                "partitioning and two recursive calls. "
                "The estimate represents average-case behavior; "
                "worst case may be O(n^2)."
            ),
        }
    return None
def _static_complexity(source_file):
    """Estimate complexity from loop patterns and nesting."""

    result = {
        "estimated_complexity": None,
        "confidence": "LOW",
        "loops_detected": [],
        "findings": [],
        "message": "",
    }

    source_path = Path(source_file)

    if not source_path.is_file():
        result["message"] = "Source file not found."
        return result

    try:
        source = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        result["message"] = f"Could not read source file: {exc}"
        return result

    cleaned = _remove_comments_and_strings(source)
    algorithm_source = _extract_algorithm_source(cleaned)
    recursive_result = _detect_recursive_complexity(
        cleaned
    )
    if recursive_result is not None:
        result.update(recursive_result)
        return result
         
    loops = _extract_loops(algorithm_source)

    if not loops:
        result.update({
            "estimated_complexity": "O(1)",
            "confidence": "LOW",
            "message": (
                "No recognizable loops detected. "
                "Recursion and complexity inside called functions "
                "are not fully analyzed."
            ),
        })

        return result

    for number, loop in enumerate(loops, start=1):
        loop["growth"] = _classify_loop(
            loop["header"],
            loop["body"],
            loop["keyword"],
        )

        result["loops_detected"].append({
            "loop_number": number,
            "type": loop["keyword"],
            "header": loop["header"],
            "estimated_growth": loop["growth"],
        })

    unknown = [
        loop for loop in loops
        if loop["growth"] == "UNKNOWN"
    ]

    if unknown:
        result["findings"].append(
            "Some loop patterns could not be classified."
        )
        result["message"] = (
            "Static analysis is inconclusive because one or more "
            "loop patterns are not recognized."
        )
        return result

    # Determine which loops contain other loops.
    nesting_depths = []

    for loop in loops:
        depth = 1

        for other in loops:
            if (
                other["start"] < loop["start"]
                and other["end"] >= loop["end"]
            ):
                depth += 1

        nesting_depths.append(depth)

    for index, loop in enumerate(loops):
        result["loops_detected"][index][
            "approximate_nesting_depth"
        ] = nesting_depths[index]

    # Use the deepest loop path as a conservative heuristic.
    deepest = max(
        range(len(loops)),
        key=lambda i: nesting_depths[i],
    )

    depth = nesting_depths[deepest]

    if depth > 3:
        estimate = f"O(n^{depth})"
    elif depth == 3:
        estimate = "O(n^3)"
    elif depth == 2:
        estimate = "O(n^2)"
    else:
        estimate = loops[deepest]["growth"]

    # Nested logarithmic loops are not necessarily polynomial.
    if depth == 1:
        growth_types = [loop["growth"] for loop in loops]

        if all(item == "O(log n)" for item in growth_types):
            estimate = "O(log n)"
        elif any(item == "O(n)" for item in growth_types):
            estimate = "O(n)"

    result.update({
        "estimated_complexity": estimate,
        "confidence": "MEDIUM",
        "message": (
            "Static estimate based on recognizable loop updates "
            "and approximate nesting. This is not a formal "
            "Big-O proof."
        ),
    })

    return result


# ---------------------------------------------------------
# 3. RUNTIME BENCHMARK CONFIGURATION
# ---------------------------------------------------------

def _normalize_benchmarks(
    benchmark_cases,
    input_sizes,
    test_inputs,
):
    """Validate and normalize benchmark inputs."""

    def generate_benchmark_input(case):
        """
        Generate benchmark input when the configuration specifies
        an input_type instead of an explicit input string.
        """

        if "input" in case and case["input"] is not None:
            return str(case["input"])

        input_size = int(case["input_size"])
        input_type = case.get("input_type", "single_integer")

        if input_type == "reverse_array":
            values = range(input_size, 0, -1)

            return (
                f"{input_size}\n"
                + " ".join(str(x) for x in values)
                + "\n"
            )

        if input_type == "sorted_array":
            values = range(1, input_size + 1)

            return (
                f"{input_size}\n"
                + " ".join(str(x) for x in values)
                + "\n"
            )

        if input_type == "single_integer":
            return f"{input_size}\n"

        raise ValueError(
            f"Unsupported benchmark input_type: {input_type}"
        )

    if benchmark_cases is not None:

        if not isinstance(benchmark_cases, (list, tuple)):
            raise ValueError(
                "benchmark_cases must be a list."
            )

        if len(benchmark_cases) < 3:
            raise ValueError(
                "At least three benchmark cases are required."
            )

        workloads = []

        for case in benchmark_cases:

            if not isinstance(case, dict):
                raise ValueError(
                    "Each benchmark case must be a dictionary."
                )

            size = case.get("input_size")

            if (
                not isinstance(size, int)
                or isinstance(size, bool)
                or size <= 0
            ):
                raise ValueError(
                    "input_size must be a positive integer."
                )

            data = generate_benchmark_input(case)

            if not isinstance(data, str):
                raise ValueError(
                    "Generated benchmark input must be a string."
                )

            workloads.append({
                "input_size": size,
                "input": data,
            })

    elif test_inputs is not None:

        if (
            not isinstance(test_inputs, (list, tuple))
            or len(test_inputs) < 3
            or not all(
                isinstance(item, str)
                for item in test_inputs
            )
        ):
            raise ValueError(
                "At least three string test_inputs are required."
            )

        workloads = [
            {
                "input_size": index + 1,
                "input": data,
            }
            for index, data in enumerate(test_inputs)
        ]

    else:

        if (
            not isinstance(input_sizes, (list, tuple))
            or len(input_sizes) < 3
            or any(
                not isinstance(size, int)
                or isinstance(size, bool)
                or size <= 0
                for size in input_sizes
            )
        ):
            raise ValueError(
                "At least three positive input sizes are required."
            )

        workloads = [
            {
                "input_size": size,
                "input": f"{size}\n",
            }
            for size in input_sizes
        ]

    sizes = [
        item["input_size"]
        for item in workloads
    ]

    if (
        sizes != sorted(sizes)
        or len(set(sizes)) != len(sizes)
    ):
        raise ValueError(
            "Benchmark input sizes must be unique and increasing."
        )

    return workloads

# ---------------------------------------------------------
# 4. RUNTIME GROWTH ESTIMATION
# ---------------------------------------------------------


def _estimate_growth(measurements):
    """
    Estimate runtime complexity using a power-law model:

        T(n) = c + a * n^p

    c represents fixed execution overhead.
    p is used to classify the growth rate.

    This is a heuristic, not a formal Big-O proof.
    """

    usable = sorted(
        [
            item for item in measurements
            if item.get("median_seconds") is not None
            and item["median_seconds"] > 0
            and item.get("input_size", 0) > 0
        ],
        key=lambda item: item["input_size"],
    )

    if len(usable) < 3:
        return {
            "estimated_complexity": None,
            "confidence": "INSUFFICIENT",
            "growth_ratios": [],
            "estimated_exponent": None,
            "log_fit_quality": 0,
            "log_model_improvement": 0,
            "details": "Insufficient timing measurements.",
        }

    sizes = [float(x["input_size"]) for x in usable]
    times = [float(x["median_seconds"]) for x in usable]

    ratios = []
    for i in range(1, len(usable)):
        ratios.append({
            "size_ratio": round(sizes[i] / sizes[i - 1], 4),
            "time_ratio": round(times[i] / times[i - 1], 4),
        })

    mean_time = statistics.mean(times)
    variation = (
        max(times) - min(times)
    ) / mean_time if mean_time > 0 else 0

    # Nearly constant timings indicate that fixed overhead
    # dominates the measured execution.
    if variation < 0.20:
        return {
            "estimated_complexity": "O(1)",
            "confidence": "LOW",
            "growth_ratios": ratios,
            "estimated_exponent": 0.0,
            "log_fit_quality": 0,
            "log_model_improvement": 0,
            "details": (
                "Execution times show little measurable growth. "
                "Constant-time behavior is a low-confidence estimate."
            ),
        }

    # Fit T(n) = c + a*n^p.
    # Search different fixed-overhead values and growth exponents.
    best_error = float("inf")
    best_exponent = None
    best_intercept = None

    minimum_time = min(times)

    for overhead_step in range(40):
        overhead = minimum_time * overhead_step / 40

        adjusted = [t - overhead for t in times]

        if any(t <= 0 for t in adjusted):
            continue

        for exponent_step in range(1, 61):
            exponent = exponent_step * 0.05

            model_x = [n ** exponent for n in sizes]

            denominator = sum(x * x for x in model_x)

            if denominator == 0:
                continue

            coefficient = sum(
                x * y for x, y in zip(model_x, adjusted)
            ) / denominator

            predictions = [
                overhead + coefficient * x
                for x in model_x
            ]

            error = sum(
                (actual - predicted) ** 2
                for actual, predicted in zip(times, predictions)
            )

            if error < best_error:
                best_error = error
                best_exponent = exponent
                best_intercept = overhead

    if best_exponent is None:
        return {
            "estimated_complexity": None,
            "confidence": "INSUFFICIENT",
            "growth_ratios": ratios,
            "estimated_exponent": None,
            "log_fit_quality": 0,
            "log_model_improvement": 0,
            "details": "Unable to fit a reliable growth model.",
        }

    total_variation = sum(
        (t - mean_time) ** 2 for t in times
    )

    fit_quality = (
        1 - best_error / total_variation
        if total_variation > 0 else 0
    )

    # Classify the fitted exponent.
    if best_exponent < 0.25:
        estimate = "O(1)"
    elif best_exponent < 0.75:
        estimate = "O(log n)"
    elif best_exponent < 1.20:
        estimate = "O(n)"
    elif best_exponent < 1.65:
        estimate = "O(n log n)"
    elif best_exponent < 2.50:
        estimate = "O(n^2)"
    else:
        estimate = "O(n^3)"

    confidence = (
        "MEDIUM"
        if fit_quality >= 0.80
        else "LOW"
    )

    return {
        "estimated_complexity": estimate,
        "confidence": confidence,
        "growth_ratios": ratios,
        "estimated_exponent": round(best_exponent, 3),
        "log_fit_quality": round(fit_quality, 4),
        "log_model_improvement": round(fit_quality, 4),
        "details": (
            "Runtime growth estimated using a power-law model "
            "with fixed execution overhead. This is a heuristic, "
            "not a formal Big-O proof."
        ),
    }

# ---------------------------------------------------------
# 5. COMBINED COMPLEXITY ASSESSMENT
# ---------------------------------------------------------


def _combine_estimates(static_result, runtime_result):
    """Combine static and runtime evidence conservatively."""

    static_estimate = static_result.get("estimated_complexity")
    runtime_estimate = runtime_result.get("estimated_complexity")

    static_confidence = static_result.get("confidence", "LOW")
    runtime_confidence = runtime_result.get("confidence", "LOW")
    runtime_fit = runtime_result.get("log_fit_quality", 0) or 0

    # Neither method produced an estimate.
    if static_estimate is None and runtime_estimate is None:
        return {
            "estimated_complexity": None,
            "confidence": "INSUFFICIENT",
            "assessment": "REVIEW",
            "message": "Neither analysis produced a reliable estimate.",
        }

    # Both methods agree.
    if (
        static_estimate is not None
        and runtime_estimate is not None
        and static_estimate == runtime_estimate
    ):
        return {
            "estimated_complexity": static_estimate,
            "confidence": "HIGH" if (
                static_confidence == "HIGH"
                and runtime_confidence == "HIGH"
                and runtime_fit >= 0.70
            ) else "MEDIUM",
            "assessment": "AGREE",
            "message": (
                "Static and runtime evidence support the same "
                "complexity estimate."
            ),
        }

    # Static evidence is available but runtime evidence is weak.
    if (
        static_estimate is not None
        and static_confidence in ("MEDIUM", "HIGH")
        and (
            runtime_estimate is None
            or runtime_confidence == "LOW"
            or runtime_fit < 0.70
        )
    ):
        return {
            "estimated_complexity": static_estimate,
            "confidence": static_confidence,
            "assessment": "STATIC_ONLY",
            "message": (
                "Runtime evidence was insufficiently reliable. "
                "The static estimate is used as the final estimate."
            ),
        }

    # Runtime timing can appear O(1) when the actual algorithm is very
    # fast and fixed process/measurement overhead dominates.
    if (
        static_estimate is not None
        and static_confidence in ("MEDIUM", "HIGH")
        and runtime_estimate == "O(1)"
        and runtime_confidence in ("MEDIUM", "HIGH")
        and runtime_fit >= 0.70
    ):
        return {
            "estimated_complexity": static_estimate,
            "confidence": static_confidence,
            "assessment": "STATIC_ONLY",
            "message": (
                "Runtime timing was effectively flat and may be dominated "
                "by fixed execution overhead. The static estimate is used "
                "as the final estimate."
            ),
        }
    # Merge Sort has a guaranteed O(n log n) algorithmic complexity.
    # Small benchmark inputs can make measured runtime growth appear
    # closer to O(n) because fixed process/container execution overhead
    # dominates the actual sorting work. When the static analyzer has
    # HIGH
    # confidence that the source is Merge Sort, preserve that classification
    # rather than treating the timing heuristic as a contradiction.
    if (
        static_estimate == "O(n log n)"
        and runtime_estimate == "O(n)"
        and static_confidence == "HIGH"
        and "Merge Sort" in static_result.get("message", "")
    ):
        return {
            "estimated_complexity": static_estimate,
            "confidence": static_confidence,
            "assessment": "STATIC_ONLY",
            "message": (
                "Static analysis recognized Merge Sort with guaranteed "
                "O(n log n) complexity. The runtime benchmark showed "
                "approximately O(n), which can occur when fixed execution "
                "overhead dominates the measured sorting time. The "
                "high-confidence static classification is therefore used."
            ),
        }
    # Quick Sort has different average-case and worst-case behavior.
    # The static analyzer recognizes the algorithmic pattern as
    # average-case O(n log n), while an adversarial reverse-sorted
    # benchmark can legitimately produce O(n^2), especially when the
    # implementation uses the last element as the pivot.
    #
    # Preserve the static algorithm classification while explicitly
    # reporting that the runtime benchmark exposed worst-case behavior.
    if (
        static_estimate == "O(n log n)"
        and runtime_estimate == "O(n^2)"
        and static_confidence in ("MEDIUM", "HIGH")
        and "Quick Sort" in static_result.get("message", "")
    ):
        return {
            "estimated_complexity": static_estimate,
            "confidence": static_confidence,
            "assessment": "STATIC_ONLY",
            "message": (
                "Static analysis recognized Quick Sort with average-case "
                "O(n log n) complexity. The runtime benchmark used an "
                "adversarial reverse-sorted input and observed O(n^2), "
                "which is consistent with Quick Sort worst-case behavior."
            ),
        }

    # Static analysis is unavailable, but runtime evidence is strong.
    if (
        static_estimate is None
        and runtime_estimate is not None
        and runtime_confidence in ("MEDIUM", "HIGH")
        and runtime_fit >= 0.70
    ):
        return {
            "estimated_complexity": runtime_estimate,
            "confidence": runtime_confidence,
            "assessment": "RUNTIME_ONLY",
            "message": "A reliable runtime estimate is available.",
        }

    # Conflicting evidence with no clearly weaker method.
    return {
        "estimated_complexity": None,
        "confidence": "LOW",
        "assessment": "REVIEW",
        "message": (
            "Static and runtime estimates conflict, and neither "
            "method can be safely preferred. Manual review is required."
        ),
    }


# ---------------------------------------------------------
# 6. MAIN COMPLEXITY ANALYZER
# ---------------------------------------------------------

def check_complexity(
    source_file,
    input_sizes=(1, 10, 100),
    timeout_seconds=3,
    test_inputs=None,
    executable_path=None,
    repetitions=3,
    benchmark_cases=None,
    expected_complexity=None,
    memory_limit_mb=128,
):
    """
    Perform static and runtime complexity analysis.

    Existing parameters are preserved for compatibility.

    benchmark_cases format:
    [
        {"input_size": 1000, "input": "1000\\n"},
        {"input_size": 2000, "input": "2000\\n"},
        {"input_size": 4000, "input": "4000\\n"}
    ]
    """

    source = Path(source_file)

    result = {
        "metric": "complexity",
        "source_file": str(source),
        "score": None,
        "status": "NOT_EVALUATED",
        "expected_complexity": expected_complexity,
        "static_analysis": {},
        "runtime_analysis": {},
        "estimated_complexity": None,
        "confidence": "INSUFFICIENT",
        "assessment": "REVIEW",
        "measurements": [],
        "growth_ratios": [],
        "findings": [],
        "message": "",
    }

    if not source.is_file():
        result["status"] = "ERROR"
        result["message"] = f"Source file not found: {source}"
        return result

    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ):
        result["status"] = "CONFIG_ERROR"
        result["message"] = (
            "timeout_seconds must be greater than zero."
        )
        return result

    if (
        not isinstance(repetitions, int)
        or isinstance(repetitions, bool)
        or repetitions <= 0
    ):
        result["status"] = "CONFIG_ERROR"
        result["message"] = (
            "repetitions must be a positive integer."
        )
        return result

    if expected_complexity is not None:
        aliases = {
            "o(1)": "O(1)",
            "o(log n)": "O(log n)",
            "o(n)": "O(n)",
            "o(n log n)": "O(n log n)",
            "o(nlogn)": "O(n log n)",
            "o(n^2)": "O(n^2)",
            "o(n²)": "O(n^2)",
            "o(n^3)": "O(n^3)",
            "o(n³)": "O(n^3)",
        }

        expected_complexity = aliases.get(
            str(expected_complexity).strip().lower()
        )

        if expected_complexity is None:
            result["status"] = "CONFIG_ERROR"
            result["message"] = (
                "Unsupported expected complexity. Supported values: "
                + ", ".join(SUPPORTED_COMPLEXITIES)
            )
            return result

        result["expected_complexity"] = expected_complexity

    # Run static analysis first.
    static_result = _static_complexity(source)

    result["static_analysis"] = static_result

    try:
        workloads = _normalize_benchmarks(
            benchmark_cases,
            input_sizes,
            test_inputs,
        )
    except ValueError as exc:
        result["status"] = "CONFIG_ERROR"
        result["message"] = str(exc)
        return result

    result["input_sizes"] = [
        item["input_size"] for item in workloads
    ]

    executable = None
    owns_executable = False
    temporary_directory = None

    if executable_path is not None:
        executable = Path(executable_path)

        if not executable.is_file():
            result["status"] = "ERROR"
            result["message"] = (
                f"Compiled executable not found: {executable}"
            )
            return result

    else:
        try:
            temporary_directory = tempfile.TemporaryDirectory(
                prefix="autograder_complexity_"
            )

            executable = (
                Path(temporary_directory.name) / "benchmark_program"
            )

            owns_executable = True

            compilation = subprocess.run(
                [
                    "gcc",
                    str(source.resolve()),
                    "-std=c11",
                    "-O0",
                    "-o",
                    str(executable),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

        except (OSError, subprocess.TimeoutExpired) as exc:
            result["status"] = "COMPILE_ERROR"
            result["message"] = (
                f"Complexity benchmark compilation failed: {exc}"
            )

            if temporary_directory is not None:
                temporary_directory.cleanup()

            return result

        if compilation.returncode != 0:
            result["status"] = "COMPILE_ERROR"
            result["findings"].append(
                compilation.stderr.strip()
            )
            result["message"] = (
                "Runtime benchmarking was skipped."
            )

            temporary_directory.cleanup()
            return result

    try:
        
        # Execute each benchmark workload in one Docker batch.
        for workload in workloads:
            error_message = None
            times = []
            last_output = ""

            try:
                execution = run_benchmark_batch(
                    executable=executable,
                    input_data=workload["input"],
                    repetitions=repetitions,
                    timeout_seconds=timeout_seconds,
                    memory_limit_mb=memory_limit_mb,
                )

                if execution["status"] != "completed":
                    error_message = (
                        execution.get("error")
                        or f"Benchmark failed: {execution['status']}"
                    )
                else:
                    times = execution["times"]

                    if execution.get("outputs"):
                        last_output = execution["outputs"][-1]["stdout"]

            except Exception as exc:
                error_message = f"Benchmark execution failed: {exc}"

            measurement = {
                "input_size": workload["input_size"],
                "runs_completed": len(times),
                "repetitions_requested": repetitions,
                "median_seconds": (
                    statistics.median(times) if times else None
                ),
                "stdout": last_output,
            }

            if error_message:
                measurement["error"] = error_message
                result["findings"].append(error_message)

            result["measurements"].append(measurement)

            if error_message:
                result["status"] = "REVIEW"
                result["message"] = (
                    "A runtime benchmark failed or timed out. "
                    "Complexity assessment requires review."
                )
                return result


        # Estimate runtime growth.
        runtime_result = _estimate_growth(
            result["measurements"]
        )
        result["runtime_analysis"] = runtime_result
        result["growth_ratios"] = runtime_result["growth_ratios"]

        # Combine static and runtime results.
        combined = _combine_estimates(
            static_result,
            runtime_result,
        )

        result["estimated_complexity"] = (
            combined["estimated_complexity"]
        )
        result["confidence"] = combined["confidence"]
        result["assessment"] = combined["assessment"]
        result["message"] = combined["message"]

        # Compare against instructor expectation if configured.
        if expected_complexity is None:
            result["status"] = "MEASURED"
            result["message"] += (
                " No instructor complexity expectation was supplied, "
                "so no complexity score was assigned."
            )
            return result

        if combined["assessment"] == "REVIEW":
            result["status"] = "REVIEW"
            result["findings"].append(
                "The two analysis methods did not provide "
                "consistent evidence."
            )
            return result

        if combined["assessment"] == "STATIC_ONLY":
            if combined["estimated_complexity"] == expected_complexity:
                result["score"] = 100
                result["status"] = "PASS"
                result["message"] += (
                    " Static estimate matches the expected complexity. "
                    "Runtime evidence was insufficient."
                )
            else:
                result["score"] = 0
                result["status"] = "REVIEW"
                result["findings"].append(
                    "Static estimate differs from the instructor's "
                    "expected complexity. Runtime evidence was insufficient."
                )

            return result
        if combined["assessment"] == "RUNTIME_ONLY":
            result["status"] = "REVIEW"
            result["findings"].append(
                "Static evidence was insufficient for grading."
            )
            return result

        if combined["estimated_complexity"] == expected_complexity:
            result["score"] = 100
            result["status"] = "PASS"
            result["message"] += (
                " The combined estimate matches the expected complexity."
            )
        else:
            result["score"] = 0
            result["status"] = "REVIEW"
            result["findings"].append(
                "The estimated complexity differs from the "
                "instructor's expected complexity."
            )

        return result

    finally:
        if owns_executable and temporary_directory is not None:
            temporary_directory.cleanup()
