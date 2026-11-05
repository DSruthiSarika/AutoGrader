import subprocess


def check_syntax(
    source_file,
    compiler="gcc",
    standard="c11",
    flags=None
):
    """
    Check a C program using GCC compiler diagnostics.

    The compiler is run with warning flags and the selected
    C standard. No executable is generated.
    """

    if flags is None:
        flags = []

    command = [
        compiler,
        f"-std={standard}",
        *flags,
        "-fsyntax-only",
        source_file
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        return {
            "metric": "syntax",
            "score": 100,
            "status": "PASS",
            "errors": [],
            "warnings": []
        }

    diagnostics = result.stderr.strip().splitlines()

    return {
        "metric": "syntax",
        "score": 0,
        "status": "FAIL",
        "errors": diagnostics,
        "warnings": []
    }