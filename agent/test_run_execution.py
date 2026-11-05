from agent.execution import run_program

result = run_program(
    "submissions/combined_output",
    "",
    10
)

stdout_size = len(result["stdout"].encode("utf-8"))
stderr_size = len(result["stderr"].encode("utf-8"))
total_size = stdout_size + stderr_size

print("COMBINED OUTPUT LIMIT TEST")
print("--------------------------")
print("Status:", result["status"])
print("Stdout:", round(stdout_size / (1024 * 1024), 3), "MB")
print("Stderr:", round(stderr_size / (1024 * 1024), 3), "MB")
print("Combined:", round(total_size / (1024 * 1024), 3), "MB")
print("Return code:", result["return_code"])