
import re
import shutil
import subprocess
from pathlib import Path

try:
    import lizard
except ImportError:
    lizard = None


def check_structure(
    source_file,
    max_cyclomatic=8,
    max_function_length=40,
    cppcheck_path=None,
):
    """
    Analyze the structure of a C source file.

    Lizard measures cyclomatic complexity and function length.
    Cppcheck reports additional static-analysis diagnostics.

    Score policy:
      - Start at 100.
      - Deduct 10 for each function exceeding either limit.
      - Minimum score is 0.

    Cppcheck diagnostics are reported separately and do not
    change the structural score.
    """

    source = Path(source_file)

    result = {
        "metric": "structure",
        "source_file": str(source),
        "score": None,
        "status": "NOT_EVALUATED",
        "limits": {
            "max_cyclomatic": max_cyclomatic,
            "max_function_length": max_function_length,
        },
        "functions": [],
        "findings": [],
        "cppcheck": {
            "available": False,
            "diagnostics": [],
        },
    }

    if not source.is_file():
        result["message"] = f"Source file not found: {source}"
        return result

    # 1. Analyze function structure using Lizard.
    if lizard is not None:
        try:
            analysis = lizard.analyze_file(str(source))

            if getattr(analysis, "error", None):
                result["message"] = (
                    f"Lizard could not analyze the file: "
                    f"{analysis.error}"
                )
                return result

            functions = []
            violations = 0

            for function in analysis.function_list:
                complexity = function.cyclomatic_complexity
                length = function.length

                function_info = {
                    "name": function.name,
                    "cyclomatic_complexity": complexity,
                    "length": length,
                    "nloc": function.nloc,
                    "findings": [],
                }

                if complexity > max_cyclomatic:
                    function_info["findings"].append(
                        f"Cyclomatic complexity {complexity} exceeds "
                        f"limit {max_cyclomatic}"
                    )
                    violations += 1

                if length > max_function_length:
                    function_info["findings"].append(
                        f"Function length {length} exceeds "
                        f"limit {max_function_length}"
                    )
                    violations += 1

                if function_info["findings"]:
                    result["findings"].append({
                        "function": function.name,
                        "issues": function_info["findings"],
                    })

                functions.append(function_info)

            result["functions"] = functions
            result["score"] = max(0, 100 - 10 * violations)
            result["status"] = (
                "PASS" if violations == 0 else "REVIEW"
            )

        except Exception as exc:
            result["message"] = (
                f"Lizard analysis failed: {exc}"
            )
            return result

    else:
        # 2. Use a basic fallback when Lizard is unavailable.
        try:
            code = source.read_text(
                encoding="utf-8",
                errors="replace"
            )
        except OSError as exc:
            result["message"] = (
                f"Could not read source file: {exc}"
            )
            return result

        pattern = re.compile(
            r"(?m)^\s*(?:static\s+)?(?:inline\s+)?"
            r"(?:void|char|short|int|long|float|double|unsigned|"
            r"signed|size_t|bool|[A-Za-z_]\w*\s*\*)"
            r"\s+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{"
        )

        names = pattern.findall(code)

        if not names:
            result["message"] = (
                "Lizard is unavailable and the fallback "
                "could not detect C function definitions."
            )
            return result

        result["functions"] = [
            {
                "name": name,
                "cyclomatic_complexity": None,
                "length": None,
                "nloc": None,
                "findings": [
                    "Approximate fallback analysis. "
                    "Detailed structural metrics are unavailable."
                ],
            }
            for name in names
        ]

        result["status"] = "HEURISTIC_FALLBACK"
        result["message"] = (
            "Lizard is unavailable. Basic function detection "
            "was performed, but a reliable structural score "
            "could not be calculated."
        )

    # 3. Run Cppcheck independently of Lizard.
    executable = (
        cppcheck_path
        or shutil.which("cppcheck")
        or shutil.which("cppcheck.exe")
    )

    if not executable:
        result["cppcheck"]["message"] = (
            "Cppcheck was not found on PATH."
        )
        return result

    result["cppcheck"]["available"] = True

    try:
        check = subprocess.run(
            [
                executable,
                "--enable=warning,style,performance,portability",
                "--template=gcc",
                str(source.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = "\n".join(
            part.strip()
            for part in (check.stdout, check.stderr)
            if part.strip()
        )

        result["cppcheck"].update({
            "return_code": check.returncode,
            "diagnostics": (
                output.splitlines() if output else []
            ),
            "status": (
                "COMPLETED"
                if check.returncode == 0
                else "CHECK_OUTPUT"
            ),
        })

    except subprocess.TimeoutExpired:
        result["cppcheck"]["status"] = "TIMEOUT"
        result["cppcheck"]["message"] = (
            "Cppcheck exceeded the 30-second time limit."
        )

    except OSError as exc:
        result["cppcheck"]["status"] = "ERROR"
        result["cppcheck"]["message"] = str(exc)

    return result
