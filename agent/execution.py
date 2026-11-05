import os
import signal
import subprocess
import time
import shutil
from pathlib import Path


DEFAULT_OUTPUT_LIMIT_MB = 5
DOCKER_IMAGE = "gcc:latest"


def _terminate_process(process):
    """Terminate the process and its child processes."""
    if process.poll() is not None:
        return

    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()

        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()

    except (ProcessLookupError, OSError):
        try:
            process.kill()
        except OSError:
            pass


def _run_command(command, input_data, timeout_seconds, output_limit):
    """Execute a command with bounded combined output and timeout enforcement."""
    import selectors

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        start_new_session=True,
    )

    stdout_data = bytearray()
    stderr_data = bytearray()

    input_bytes = (
        input_data.encode("utf-8")
        if isinstance(input_data, str)
        else input_data
    )

    input_offset = 0
    start_time = time.monotonic()
    status = None

    try:
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdout.fileno(), False)
            os.set_blocking(process.stderr.fileno(), False)
            os.set_blocking(process.stdin.fileno(), False)

            selector.register(
                process.stdout, selectors.EVENT_READ, "stdout"
            )
            selector.register(
                process.stderr, selectors.EVENT_READ, "stderr"
            )

            if input_bytes:
                selector.register(
                    process.stdin, selectors.EVENT_WRITE, "stdin"
                )
            else:
                process.stdin.close()

            while selector.get_map():

                if time.monotonic() - start_time > timeout_seconds:
                    status = "timeout"
                    _terminate_process(process)
                    break

                events = selector.select(timeout=0.05)

                for key, _ in events:
                    stream = key.fileobj
                    name = key.data

                    if name == "stdin":
                        try:
                            written = os.write(
                                stream.fileno(),
                                input_bytes[
                                    input_offset:input_offset + 65536
                                ],
                            )

                            input_offset += written

                            if input_offset >= len(input_bytes):
                                selector.unregister(stream)
                                stream.close()

                        except BrokenPipeError:
                            selector.unregister(stream)
                            stream.close()

                    else:
                        try:
                            chunk = os.read(stream.fileno(), 65536)
                        except OSError:
                            chunk = b""

                        if not chunk:
                            selector.unregister(stream)
                            stream.close()
                            continue

                        target = (
                            stdout_data
                            if name == "stdout"
                            else stderr_data
                        )

                        remaining = (
                            output_limit
                            - len(stdout_data)
                            - len(stderr_data)
                        )

                        if len(chunk) > remaining:
                            if remaining > 0:
                                target.extend(chunk[:remaining])

                            status = "output_limit_exceeded"
                            _terminate_process(process)
                            break

                        target.extend(chunk)

                if status:
                    break

                if process.poll() is not None and not selector.get_map():
                    break

        if status is None:
            try:
                process.wait(timeout=max(0.1, timeout_seconds))
            except subprocess.TimeoutExpired:
                status = "timeout"
                _terminate_process(process)

    finally:
        if process.poll() is None:
            _terminate_process(process)

        for stream in (
            process.stdin,
            process.stdout,
            process.stderr,
        ):
            if stream and not stream.closed:
                stream.close()

    stdout = stdout_data.decode("utf-8", errors="replace")
    stderr = stderr_data.decode("utf-8", errors="replace")

    if status == "timeout":
        stderr += "\nProgram exceeded the time limit."

    if status == "output_limit_exceeded":
        # Reserve space for the termination message.
        # This guarantees stdout + stderr remain within output_limit.
        marker = "\nProgram exceeded the output size limit."
        marker_size = len(marker.encode("utf-8"))

        available = max(0, output_limit - marker_size)

        stdout_bytes = stdout.encode("utf-8")
        stderr_bytes = stderr.encode("utf-8")

        if len(stdout_bytes) + len(stderr_bytes) > available:
            stdout_bytes = stdout_bytes[:available]

            remaining = max(0, available - len(stdout_bytes))
            stderr_bytes = stderr_bytes[:remaining]

        stdout = stdout_bytes.decode("utf-8", errors="ignore")
        stderr = (
            stderr_bytes.decode("utf-8", errors="ignore")
            + marker
        )

    return {
        "status": status or (
            "completed"
            if process.returncode == 0
            else "runtime_error"
        ),
        "return_code": (
            None if status == "timeout" else process.returncode
        ),
        "stdout": stdout,
        "stderr": stderr,
        "message": (
            "Program exceeded the output size limit."
            if status == "output_limit_exceeded"
            else ""
        ),
    }


def _is_linux_executable(executable):
    """Identify Linux ELF executables."""
    try:
        with open(executable, "rb") as file:
            return file.read(4) == b"\x7fELF"
    except OSError:
        return False


def _run_docker(
    executable,
    input_data,
    timeout_seconds,
    memory_limit_mb,
    output_limit,
):
    """Run a Linux executable inside Docker and clean up its container."""

    docker = os.environ.get("DOCKER_PATH", "docker")
    executable_path = Path(executable).resolve()

    container_name = (
        f"autograder-{os.getpid()}-{time.time_ns()}"
    )

    command = [
        docker,
        "run",
        "--rm",
        "--name",
        container_name,
        "--interactive",
        "--network=none",
        f"--memory={memory_limit_mb}m",
        f"--memory-swap={memory_limit_mb}m",
        "--cpus=1",
        "--pids-limit=64",
        "--mount",
        f"type=bind,source={executable_path.parent},target=/work,readonly",
        "-w",
        "/work",
        "--entrypoint",
        f"/work/{executable_path.name}",
        DOCKER_IMAGE,
    ]

    try:
        result = _run_command(
            command,
            input_data,
            timeout_seconds,
            output_limit,
        )

        result["memory_limit_status"] = "ENFORCED"
        return result

    finally:
        # Remove containers left behind if the Docker client is killed.
        try:
            subprocess.run(
                [docker, "rm", "-f", container_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def run_program(
    executable,
    input_data,
    timeout_seconds,
    memory_limit_mb=None,
    output_limit_mb=DEFAULT_OUTPUT_LIMIT_MB,
):
    """
    Execute a program.

    Linux ELF executables run inside Docker with memory limits.
    Native executables use the POSIX execution path without
    memory-limit enforcement.
    """

    if (
        not isinstance(timeout_seconds, (int, float))
        or isinstance(timeout_seconds, bool)
        or timeout_seconds <= 0
    ):
        return {
            "status": "error",
            "return_code": None,
            "stdout": "",
            "stderr": "Timeout must be a positive number.",
        }

    if (
        not isinstance(output_limit_mb, (int, float))
        or isinstance(output_limit_mb, bool)
        or output_limit_mb <= 0
    ):
        return {
            "status": "error",
            "return_code": None,
            "stdout": "",
            "stderr": "Output limit must be a positive number.",
        }

    if memory_limit_mb is not None and (
        not isinstance(memory_limit_mb, (int, float))
        or isinstance(memory_limit_mb, bool)
        or memory_limit_mb <= 0
    ):
        return {
            "status": "error",
            "return_code": None,
            "stdout": "",
            "stderr": "Memory limit must be a positive number.",
        }

    executable_path = Path(executable)

    if not executable_path.is_file():
        return {
            "status": "error",
            "return_code": None,
            "stdout": "",
            "stderr": f"Executable not found: {executable}",
        }

    output_limit = int(output_limit_mb * 1024 * 1024)

    try:
        # Linux ELF executable: use Docker.
        if _is_linux_executable(executable_path):

            effective_memory_limit = (
                int(memory_limit_mb)
                if memory_limit_mb is not None
                else 128
            )

            return _run_docker(
                executable_path,
                input_data,
                timeout_seconds,
                effective_memory_limit,
                output_limit,
            )

        # Native POSIX executable: memory limit is not enforced.
        if os.name == "posix":

            result = _run_command(
                [str(executable_path)],
                input_data,
                timeout_seconds,
                output_limit,
            )

            result["memory_limit_status"] = "NOT_ENFORCED"

            return result

        # Non-POSIX fallback.
        result = subprocess.run(
            [str(executable_path)],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            errors="replace",
        )

        return {
            "status": (
                "completed"
                if result.returncode == 0
                else "runtime_error"
            ),
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "memory_limit_status": "NOT_ENFORCED",
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "return_code": None,
            "stdout": "",
            "stderr": "Program exceeded the time limit.",
            "memory_limit_status": "NOT_ENFORCED",
        }

    except OSError as exc:
        return {
            "status": "error",
            "return_code": None,
            "stdout": "",
            "stderr": str(exc),
            "memory_limit_status": "NOT_ENFORCED",
        }


def _generate_benchmark_input(case):
    """
    Generate benchmark input from either an explicit input string
    or a supported benchmark generator specification.

    Supported input types:
        - reverse_array
        - sorted_array
        - single_integer
    """

    # Preserve explicitly supplied benchmark input.
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


def run_benchmark_batch(
    executable,
    input_data,
    repetitions=3,
    timeout_seconds=3,
    memory_limit_mb=128,
    output_limit_mb=10,
):
    """
    Run repeated benchmarks using Docker for Linux or native execution
    on macOS.

    For Linux ELF executables:
        - execution happens inside Docker
        - memory limit is enforced
        - CPU limit is enforced
        - PID limit is enforced
        - network is disabled
        - each repetition has its own input
        - execution time is measured inside the container

    For native macOS executables:
        - execution is performed directly
        - memory limits are not enforced
        - this path is intended mainly for unit tests
    """

    import tempfile
    import uuid

    executable_path = Path(executable).resolve()

    if not executable_path.is_file():
        return {
            "status": "error",
            "error": f"Executable not found: {executable_path}",
            "times": [],
            "outputs": [],
        }

    repetitions = max(1, int(repetitions))
    timeout_seconds = max(1, float(timeout_seconds))
    output_limit_bytes = int(output_limit_mb * 1024 * 1024)

    # Normalize input.
    if isinstance(input_data, str):
        input_bytes = input_data.encode("utf-8")
    else:
        input_bytes = input_data

    # ---------------------------------------------------------
    # Native macOS execution
    # ---------------------------------------------------------
    # Used mainly by unit tests because macOS executables are
    # Mach-O rather than Linux ELF.
    if not _is_linux_executable(executable_path):

        times = []
        outputs = []

        for _ in range(repetitions):

            start = time.perf_counter()

            try:
                completed = subprocess.run(
                    [str(executable_path)],
                    input=input_bytes,
                    capture_output=True,
                    timeout=timeout_seconds,
                )

            except subprocess.TimeoutExpired:
                return {
                    "status": "timeout",
                    "error": "Native benchmark timed out.",
                    "times": times,
                    "outputs": outputs,
                }

            except OSError as exc:
                return {
                    "status": "error",
                    "error": str(exc),
                    "times": times,
                    "outputs": outputs,
                }

            elapsed = time.perf_counter() - start

            stdout = completed.stdout
            stderr = completed.stderr

            if len(stdout) + len(stderr) > output_limit_bytes:
                return {
                    "status": "output_limit_exceeded",
                    "error": "Benchmark output exceeded the configured limit.",
                    "times": times,
                    "outputs": outputs,
                }

            outputs.append({
                "stdout": stdout.decode(
                    "utf-8",
                    errors="replace",
                ),
                "stderr": stderr.decode(
                    "utf-8",
                    errors="replace",
                ),
                "return_code": completed.returncode,
            })

            if completed.returncode != 0:
                return {
                    "status": "runtime_error",
                    "error": stderr.decode(
                        "utf-8",
                        errors="replace",
                    )[-2000:],
                    "times": times,
                    "outputs": outputs,
                }

            times.append(elapsed)

        return {
            "status": "completed",
            "times": times,
            "outputs": outputs,
            "memory_limit_status": "NOT_ENFORCED_NATIVE_TEST",
        }

    # ---------------------------------------------------------
    # Linux execution
    # ---------------------------------------------------------
    # Use Docker resource limits.
    docker = shutil.which("docker")

    if not docker:
        return {
            "status": "error",
            "error": "Docker CLI was not found.",
            "times": [],
            "outputs": [],
        }

    container_name = (
        f"autograder-bench-{uuid.uuid4().hex[:12]}"
    )

    with tempfile.TemporaryDirectory(
        prefix="autograder_bench_",
        dir=str(Path.cwd()),
    ) as temporary_directory:

        bench_dir = Path(temporary_directory)

        # Copy executable into the mounted benchmark directory.
        benchmark_executable = bench_dir / "program"
        shutil.copy2(
            executable_path,
            benchmark_executable,
        )
        benchmark_executable.chmod(0o755)

        results_dir = bench_dir / "results"
        results_dir.mkdir()

        # Create one input file per repetition.
        for index in range(repetitions):
            (bench_dir / f"input_{index}").write_bytes(
                input_bytes
            )

        # -----------------------------------------------------
        # Benchmark script
        # -----------------------------------------------------
        # The program output is redirected to files so that the
        # host process does not need to continuously consume it.
        # The actual correctness tests separately validate output.
        script = r'''
set +e

i=0

while [ "$i" -lt "@@REPETITIONS@@" ]; do

    start=$(date +%s%N)

    timeout --signal=KILL "@@TIMEOUT@@s" \
        /bench/program \
        < "/bench/input_${i}" \
        > /dev/null \
        2> /dev/null

    code=$?

    end=$(date +%s%N)

    elapsed=$((end - start))

    echo "$elapsed $code" >> /bench/results/timings.txt

    if [ "$code" -ne 0 ]; then
        exit "$code"
    fi

    i=$((i + 1))

done

exit 0
'''

        # Replace placeholders safely.
        script = (
            script
            .replace(
                "@@REPETITIONS@@",
                str(repetitions),
            )
            .replace(
                "@@TIMEOUT@@",
                str(timeout_seconds),
            )
        )

        command = [
            docker,
            "run",
            "--rm",
            "--name",
            container_name,
            "--network=none",
            f"--memory={memory_limit_mb}m",
            f"--memory-swap={memory_limit_mb}m",
            "--cpus=1",
            "--pids-limit=64",
            "--mount",
            f"type=bind,source={bench_dir},target=/bench",
            "--entrypoint",
            "/bin/sh",
            "gcc:latest",
            "-c",
            script,
        ]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=(timeout_seconds * repetitions) + 15,
            )

            timings_file = results_dir / "timings.txt"

            if not timings_file.exists():
                return {
                    "status": (
                        "timeout"
                        if completed.returncode == 124
                        else "runtime_error"
                    ),
                    "error": completed.stderr[-2000:],
                    "times": [],
                    "outputs": [],
                }

            times = []
            outputs = []

            for index, line in enumerate(
                timings_file.read_text().splitlines()
            ):

                parts = line.split()

                if len(parts) != 2:
                    continue

                elapsed_ns = int(parts[0])
                return_code = int(parts[1])

                output_file = (
                    results_dir / f"out_{index}"
                )

                error_file = (
                    results_dir / f"err_{index}"
                )

                stdout = (
                    output_file.read_bytes()
                    if output_file.exists()
                    else b""
                )

                stderr = (
                    error_file.read_bytes()
                    if error_file.exists()
                    else b""
                )

                if (
                    len(stdout) + len(stderr)
                    > output_limit_bytes
                ):
                    return {
                        "status": "output_limit_exceeded",
                        "error": (
                            "Benchmark output exceeded "
                            "the configured limit."
                        ),
                        "times": times,
                        "outputs": outputs,
                    }

                outputs.append({
                    "stdout": stdout.decode(
                        "utf-8",
                        errors="replace",
                    ),
                    "stderr": stderr.decode(
                        "utf-8",
                        errors="replace",
                    ),
                    "return_code": return_code,
                })

                if return_code != 0:
                    return {
                        "status": (
                            "timeout"
                            if return_code in (124, 137)
                            else "runtime_error"
                        ),
                        "error": stderr.decode(
                            "utf-8",
                            errors="replace",
                        )[-2000:],
                        "times": times,
                        "outputs": outputs,
                    }

                times.append(
                    elapsed_ns / 1_000_000_000
                )

            if len(times) != repetitions:
                return {
                    "status": "runtime_error",
                    "error": (
                        "Not all benchmark repetitions completed."
                    ),
                    "times": times,
                    "outputs": outputs,
                }

            return {
                "status": "completed",
                "times": times,
                "outputs": outputs,
                "memory_limit_status": "ENFORCED",
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "error": (
                    "Benchmark batch exceeded "
                    "its total time limit."
                ),
                "times": [],
                "outputs": [],
            }

        except (
            OSError,
            subprocess.SubprocessError,
        ) as exc:
            return {
                "status": "error",
                "error": str(exc),
                "times": [],
                "outputs": [],
            }

        finally:
            try:
                subprocess.run(
                    [
                        docker,
                        "rm",
                        "-f",
                        container_name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except (
                OSError,
                subprocess.TimeoutExpired,
            ):
                pass