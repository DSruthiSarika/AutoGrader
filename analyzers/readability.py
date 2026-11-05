import re
import shutil
import subprocess
from pathlib import Path

MAX_LINE_LENGTH = 100


def check_readability(source_file, timeout_seconds=15):
    """Score readability with transparent source heuristics and optional tools."""
    source = Path(source_file)
    result = {
        "metric": "readability", "source_file": str(source), "score": None,
        "status": "NOT_EVALUATED", "findings": [], "details": {},
        "tools": [],
    }
    if not source.is_file():
        result.update(status="ERROR", message=f"Source file not found: {source}")
        return result
    try:
        code = source.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result.update(status="ERROR", message=f"Could not read source file: {exc}")
        return result
    if not code.strip():
        result.update(status="ERROR", message="Source file is empty.")
        return result

    lines = code.splitlines()
    deductions = 0
    long_lines = [i for i, line in enumerate(lines, 1) if len(line) > MAX_LINE_LENGTH]
    if long_lines:
        deductions += min(2 * len(long_lines), 20)
        result["findings"].append({"category": "formatting", "message": f"{len(long_lines)} line(s) exceed {MAX_LINE_LENGTH} characters.", "lines": long_lines})

    # Tabs are not inherently wrong, but inconsistent tab indentation is a review signal.
    tab_lines = [i for i, line in enumerate(lines, 1) if line.startswith("\t")]
    if tab_lines:
        deductions += min(len(tab_lines), 5)
        result["findings"].append({"category": "formatting", "message": "Tab indentation detected.", "lines": tab_lines})

    # Basic variable-name heuristic; intentionally not treated as proof of poor quality.
    identifiers = re.findall(r"\b(?:int|char|float|double|long|short|bool|size_t)\s+([A-Za-z_]\w*)", code)
    terse = [name for name in identifiers if len(name) == 1 and name not in {"i", "j", "k", "x", "y"}]
    if terse:
        deductions += min(2 * len(terse), 10)
        result["findings"].append({"category": "naming", "message": "Some variable names may be unclear.", "identifiers": terse})

    if not re.search(r"/\*|//", code):
        deductions += 5
        result["findings"].append({"category": "documentation", "message": "No source comments detected; comments may help explain non-obvious logic."})

    # Optional formatter check. Missing tools do not prevent the basic metric from scoring.
    formatter = shutil.which("clang-format") or shutil.which("clang-format.exe")
    if formatter:
        result["tools"].append("clang-format")
        try:
            formatted = subprocess.run([formatter, "--dry-run", "--Werror", str(source.resolve())], capture_output=True, text=True, timeout=timeout_seconds)
            result["details"]["clang_format_passed"] = formatted.returncode == 0
            if formatted.returncode != 0:
                deductions += 5
                result["findings"].append({"category": "clang-format", "message": "Formatting differs from clang-format style.", "details": (formatted.stderr or formatted.stdout).strip()})
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["findings"].append({"category": "clang-format", "message": f"Optional formatter check failed: {exc}"})

    cppcheck = shutil.which("cppcheck") or shutil.which("cppcheck.exe")
    if cppcheck:
        result["tools"].append("cppcheck")
        try:
            check = subprocess.run([cppcheck, "--enable=style", "--language=c", "--std=c11", str(source.resolve())], capture_output=True, text=True, timeout=timeout_seconds)
            raw_diagnostics = (check.stdout + "\n" + check.stderr).strip()
            result["details"]["cppcheck_return_code"] = check.returncode
            diagnostic_lines = [
                line.strip()
                for line in raw_diagnostics.splitlines()
                if re.search(
                    r":\d+:\d+:\s+(error|warning|style|performance|portability):",
                    line,
                    re.IGNORECASE,
                )
            ]
            
            if diagnostic_lines:
                result["details"]["cppcheck_diagnostics"] = diagnostic_lines

                result["findings"].append({
                "category": "cppcheck",
                "message": "Cppcheck detected a source-code diagnostic.",
                "details": "\n".join(diagnostic_lines),
                })
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["findings"].append({"category": "cppcheck", "message": f"Optional Cppcheck check failed: {exc}"})

    result["score"] = max(0, 100 - deductions)
    result["status"] = "PASS" if result["score"] >= 80 else "REVIEW"
    result["details"].update({"line_count": len(lines), "long_line_count": len(long_lines), "tab_indentation_count": len(tab_lines), "terse_identifiers": terse, "optional_tools_used": result["tools"]})
    result["message"] = "Heuristic readability estimate. Optional external tools improve coverage when installed; review findings manually."
    return result
