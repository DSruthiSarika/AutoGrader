import re
from pathlib import Path


def check_modularity(source_file, problem_config=None):
    """
    Evaluate modularity using instructor-defined problem requirements.

    Configuration:
        modularity:
            min_helper_functions: minimum required helper functions
            require_helper_calls: whether helper functions must be reachable
                                  from main() through the call graph

    A simple program is not penalized when helper functions
    are not required.
    """

    source = Path(source_file)

    result = {
        "metric": "modularity",
        "source_file": str(source),
        "score": None,
        "status": "NOT_EVALUATED",
        "functions": [],
        "findings": [],
    }

    if not source.is_file():
        result["message"] = f"Source file not found: {source}"
        return result

    try:
        code = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        result["message"] = f"Could not read source file: {exc}"
        return result

    # Remove comments and string/character literals.
    code = re.sub(
        r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
        r'|//[^\n]*|/\*.*?\*/',
        ' ',
        code,
        flags=re.DOTALL,
    )

    # Detect simple C function definitions.
    function_pattern = re.compile(
        r'^[ \t]*'
        r'(?:static[ \t]+)?'
        r'(?:inline[ \t]+)?'
        r'[\w \t\*]+?[ \t]+'
        r'([A-Za-z_]\w*)[ \t]*'
        r'\([^;{}]*\)\s*\{',
        re.MULTILINE,
    )

    control_keywords = {
        "if",
        "else",
        "for",
        "while",
        "do",
        "switch",
        "case",
        "return",
        "sizeof",
    }

    function_matches = [
        match
        for match in function_pattern.finditer(code)
        if match.group(1) not in control_keywords
    ]

    functions = [
        match.group(1)
        for match in function_matches
    ]

    result["functions"] = functions

    non_main_functions = [
        name for name in functions if name != "main"
    ]

    # Read instructor-defined requirements.
    config = (problem_config or {}).get("modularity", {})

    min_helpers = config.get("min_helper_functions", 0)
    require_calls = config.get("require_helper_calls", False)

    # Validate configuration.
    if (
        not isinstance(min_helpers, int)
        or isinstance(min_helpers, bool)
        or min_helpers < 0
    ):
        result["message"] = (
            "min_helper_functions must be a non-negative integer."
        )
        return result

    if not isinstance(require_calls, bool):
        result["message"] = (
            "require_helper_calls must be a boolean."
        )
        return result

    # ---------------------------------------------------------
    # Build a simple function call graph.
    #
    # Example:
    #
    # main -> quickSort -> partition -> swap
    #
    # A helper is considered used when it is reachable from
    # main(), not only when it is called directly by main().
    # ---------------------------------------------------------

    function_bodies = {}

    for index, match in enumerate(function_matches):
        name = match.group(1)
        opening = match.end() - 1

        brace_depth = 1
        position = opening + 1

        while position < len(code) and brace_depth > 0:
            if code[position] == "{":
                brace_depth += 1
            elif code[position] == "}":
                brace_depth -= 1
            position += 1

        if brace_depth == 0:
            function_bodies[name] = code[
                opening + 1:position - 1
            ]

    call_graph = {
        name: []
        for name in functions
    }

    for function_name, body in function_bodies.items():
        for called_name in non_main_functions:
            if called_name == function_name:
                # Ignore self-recursive calls for the purpose of
                # determining whether a helper is used.
                continue

            if re.search(
                r'\b' + re.escape(called_name) + r'\s*\(',
                body
            ):
                call_graph[function_name].append(called_name)

    # ---------------------------------------------------------
    # Find every helper reachable from main().
    # ---------------------------------------------------------

    called_helpers = []

    if "main" in call_graph:
        visited = set()
        stack = ["main"]

        while stack:
            current = stack.pop()

            if current in visited:
                continue

            visited.add(current)

            for called_name in call_graph.get(current, []):
                if called_name not in visited:
                    stack.append(called_name)

        called_helpers = [
            name
            for name in non_main_functions
            if name in visited
        ]

    missing_helpers = max(
        0, min_helpers - len(non_main_functions)
    )

    unused_helpers = [
        name
        for name in non_main_functions
        if name not in called_helpers
    ]

    score = 100

    if missing_helpers > 0:
        score -= 20 * missing_helpers
        result["findings"].append(
            f"{missing_helpers} required helper function(s) missing."
        )

    if require_calls and unused_helpers:
        score -= 10 * len(unused_helpers)
        result["findings"].append(
            "Some helper functions are not reachable from main(): "
            + ", ".join(unused_helpers)
        )

    score = max(0, min(100, score))

    result["score"] = score

    if score == 100:
        result["status"] = "PASS"

        if not non_main_functions and min_helpers == 0:
            result["findings"].append(
                "No additional helper functions are required for this problem."
            )
    else:
        result["status"] = "REVIEW"

    result["summary"] = {
        "total_functions_detected": len(functions),
        "non_main_functions_detected": len(non_main_functions),
        "called_helper_functions": called_helpers,
        "required_helper_functions": min_helpers,
    }

    result["call_graph"] = call_graph

    return result