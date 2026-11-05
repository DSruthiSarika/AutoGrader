
import os
import subprocess
import time
from pathlib import Path

import pytest

from agent.execution import run_program


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMP_DIR = PROJECT_ROOT / "tests" / "execution_temp"


@pytest.fixture(scope="module", autouse=True)
def setup_temp_directory():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    yield
    for file in TEMP_DIR.iterdir():
        if file.is_file():
            file.unlink()
    TEMP_DIR.rmdir()


def compile_program(name, code):
    source = TEMP_DIR / f"{name}.c"
    executable = TEMP_DIR / name

    source.write_text(code, encoding="utf-8")

    subprocess.run(
        ["gcc", str(source), "-o", str(executable)],
        check=True,
        capture_output=True,
        text=True,
    )

    return executable


def test_normal_execution():
    executable = compile_program(
        "normal",
        """
        #include <stdio.h>
        int main(void) {
            int a, b;
            scanf("%d %d", &a, &b);
            printf("%d\\n", a + b);
            return 0;
        }
        """,
    )

    result = run_program(str(executable), "5 7", 2)

    assert result["status"] == "completed"
    assert result["return_code"] == 0
    assert result["stdout"] == "12\n"


def test_runtime_error():
    executable = compile_program(
        "runtime_error",
        """
        int main(void) {
            return 1;
        }
        """,
    )

    result = run_program(str(executable), "", 2)

    assert result["status"] == "runtime_error"
    assert result["return_code"] == 1


def test_timeout():
    executable = compile_program(
        "infinite_loop",
        """
        int main(void) {
            while (1) {}
            return 0;
        }
        """,
    )

    start = time.monotonic()
    result = run_program(str(executable), "", 1)
    elapsed = time.monotonic() - start

    assert result["status"] == "timeout"
    assert elapsed < 4


def test_stdout_output_limit():
    executable = compile_program(
        "large_stdout",
        """
        #include <stdio.h>
        int main(void) {
            while (1) {
                printf("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\\n");
            }
            return 0;
        }
        """,
    )

    result = run_program(
        str(executable),
        "",
        5,
        output_limit_mb=1,
    )

    assert result["status"] == "output_limit_exceeded"
    assert len(result["stdout"].encode("utf-8")) <= 1024 * 1024


def test_stderr_output_limit():
    executable = compile_program(
        "large_stderr",
        """
        #include <stdio.h>
        int main(void) {
            while (1) {
                fprintf(stderr, "ERROR: AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\\n");
            }
            return 0;
        }
        """,
    )

    result = run_program(
        str(executable),
        "",
        5,
        output_limit_mb=1,
    )

    assert result["status"] == "output_limit_exceeded"
    assert len(result["stderr"].encode("utf-8")) <= 1024 * 1024
    assert result["message"] == "Program exceeded the output size limit."


def test_combined_output_limit():
    executable = compile_program(
        "combined_output",
        """
        #include <stdio.h>
        int main(void) {
            while (1) {
                printf("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\\n");
                fprintf(stderr, "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB\\n");
            }
            return 0;
        }
        """,
    )

    result = run_program(
        str(executable),
        "",
        5,
        output_limit_mb=1,
    )

    total_size = (
        len(result["stdout"].encode("utf-8"))
        + len(result["stderr"].encode("utf-8"))
    )

    assert result["status"] == "output_limit_exceeded"
    assert total_size <= 1024 * 1024
    assert result["message"] == "Program exceeded the output size limit."


def test_child_process_termination():
    if os.name != "posix":
        pytest.skip("Process-group test requires POSIX.")

    executable = compile_program(
        "child_process",
        """
        #include <stdio.h>
        #include <unistd.h>

        int main(void) {
            pid_t pid = fork();

            if (pid < 0) return 1;

            if (pid == 0) {
                while (1) sleep(1);
            }

            printf("%d\\n", pid);
            fflush(stdout);

            while (1) sleep(1);

            return 0;
        }
        """,
    )

    result = run_program(str(executable), "", 1)

    assert result["status"] == "timeout"

    child_pid = int(result["stdout"].strip().splitlines()[0])

    time.sleep(0.2)

    check = subprocess.run(
        ["ps", "-p", str(child_pid), "-o", "stat="],
        capture_output=True,
        text=True,
    )

    assert not check.stdout.strip(), (
        f"Child process {child_pid} is still present: {check.stdout}"
    )


@pytest.mark.parametrize(
    "timeout",
    [0, -1, None, "invalid", True],
)
def test_invalid_timeout(timeout):
    result = run_program(
        "submissions/correct",
        "",
        timeout,
    )

    assert result["status"] == "error"


@pytest.mark.parametrize(
    "output_limit",
    [0, -1, None, "invalid", True],
)
def test_invalid_output_limit(output_limit):
    result = run_program(
        "submissions/correct",
        "",
        2,
        output_limit_mb=output_limit,
    )

    assert result["status"] == "error"


def test_memory_limit_is_reported_as_not_enforced():
    result = run_program(
        "submissions/correct",
        "5 7",
        2,
        memory_limit_mb=128,
    )

    assert result["status"] == "completed"
    assert result["memory_limit_status"] == "NOT_ENFORCED"
