"""
Problem-configurable test generator for AutoGrader.

Supported problem types:
1. integer_pair       - addition and similar two-integer problems
2. integer_array_sort - sorting an integer array
3. linear_search      - searching for an integer in an array
4. string_reverse     - reversing a string

Expected outputs are calculated using independent Python
reference implementations, not the submitted C program.
"""

import random




def generate_integer_pair(cases):
    """Generate tests for programs reading two integers."""

    values = {
        "both_zero": (0, 0),
        "positive_numbers": (15, 25),
        "negative_numbers": (-15, -25),
        "mixed_signs": (-15, 25),
        "zero_first": (0, 25),
        "zero_second": (25, 0),
        "large_positive": (1000000, 2000000),
        "large_negative": (-1000000, -2000000),
    }

    tests = []

    for case in cases:
        if case not in values:
            raise ValueError(f"Unsupported integer_pair case: {case}")

        a, b = values[case]
        expected = a + b

        tests.append({
            "category": case,
            "input": f"{a} {b}\n",
            "expected_output": f"{expected}\n"
        })

    return tests


def generate_integer_array_sort(cases, seed=42):
    """Generate tests for sorting programs."""

    values = {
        "empty": [],
        "single": [5],
        "already_sorted": [1, 2, 3, 4, 5],
        "reverse_sorted": [5, 4, 3, 2, 1],
        "duplicates": [4, 2, 4, 1, 2],
        "negative_numbers": [-5, 3, -1, 0, 8],
        "all_equal": [7, 7, 7, 7],
    }

    rng = random.Random(seed)
    tests = []

    for case in cases:
        if case == "random":
            array = [rng.randint(-100, 100) for _ in range(20)]
        elif case in values:
            array = values[case]
        else:
            raise ValueError(f"Unsupported sorting case: {case}")

        input_data = f"{len(array)}\n"
        input_data += " ".join(map(str, array)) + "\n"

        expected = " ".join(map(str, sorted(array)))

        tests.append({
            "category": case,
            "input": input_data,
            "expected_output": expected + "\n"
        })

    return tests


def generate_linear_search(cases, seed=42):
    """Generate tests for linear search programs."""

    values = {
        "first_element": ([10, 20, 30], 10),
        "last_element": ([10, 20, 30], 30),
        "middle_element": ([10, 20, 30], 20),
        "not_found": ([10, 20, 30], 99),
        "duplicates": ([5, 2, 5, 8], 5),
        "negative_numbers": ([-5, -2, 0, 4], -2),
        "empty": ([], 10),
    }

    rng = random.Random(seed)
    tests = []

    for case in cases:
        if case == "random":
            array = [rng.randint(-100, 100) for _ in range(20)]
            target = array[10]
        elif case in values:
            array, target = values[case]
        else:
            raise ValueError(f"Unsupported searching case: {case}")

        input_data = f"{len(array)}\n"
        input_data += " ".join(map(str, array)) + "\n"
        input_data += f"{target}\n"

        expected = array.index(target) if target in array else -1

        tests.append({
            "category": case,
            "input": input_data,
            "expected_output": f"{expected}\n"
        })

    return tests


def generate_string_reverse(cases):
    """Generate tests for string-reversal programs."""

    values = {
        "normal": "hello",
        "empty": "",
        "single_character": "a",
        "palindrome": "madam",
        "spaces": "hello world",
        "numbers": "123456",
    }

    tests = []

    for case in cases:
        if case not in values:
            raise ValueError(f"Unsupported string_reverse case: {case}")

        value = values[case]

        tests.append({
            "category": case,
            "input": value + "\n",
            "expected_output": value[::-1] + "\n"
        })

    return tests


GENERATORS = {
    "integer_pair": generate_integer_pair,
    "integer_array_sort": generate_integer_array_sort,
    "linear_search": generate_linear_search,
    "string_reverse": generate_string_reverse,
}


def generate_edge_cases(config):
    """
    Generate deterministic edge cases from a problem configuration.

    Validate configuration before dispatching to a generator.
    """

    if not isinstance(config, dict):
        raise ValueError("Problem configuration must be a JSON object.")

    edge_config = config.get("edge_cases", {})

    if not isinstance(edge_config, dict):
        raise ValueError("'edge_cases' must be a JSON object.")

    enabled = edge_config.get("enabled", False)

    if not isinstance(enabled, bool):
        raise ValueError("'edge_cases.enabled' must be true or false.")

    if not enabled:
        return []

    generator_name = edge_config.get("generator")

    if not isinstance(generator_name, str):
        raise ValueError("'edge_cases.generator' must be a string.")

    if generator_name not in GENERATORS:
        raise ValueError(
            f"Unsupported generator: {generator_name}. "
            f"Available generators: {list(GENERATORS)}"
        )

    cases = edge_config.get("cases", [])

    if not isinstance(cases, list):
        raise ValueError("'edge_cases.cases' must be a list.")

    if not all(isinstance(case, str) for case in cases):
        raise ValueError("Every edge-case name must be a string.")

    seed = edge_config.get("seed", 42)

    if (
        not isinstance(seed, int)
        or isinstance(seed, bool)
    ):
        raise ValueError("'edge_cases.seed' must be an integer.")

    generator = GENERATORS[generator_name]

    if generator_name in {"integer_array_sort", "linear_search"}:
        return generator(cases, seed=seed)

    return generator(cases)



