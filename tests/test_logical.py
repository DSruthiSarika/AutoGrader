
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from analyzers.logical import check_logical


class TestLogicalEdgeCases(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        self.source = self.root / "addition.c"
        self.executable = self.root / "addition"

        self.source.write_text(
            r"""
#include <stdio.h>

int main(void) {
    int a, b;

    if (scanf("%d %d", &a, &b) != 2)
        return 1;

    printf("%d\n", a + b);

    return 0;
}
"""
        )

        subprocess.run(
            [
                "gcc",
                "-std=c11",
                str(self.source),
                "-o",
                str(self.executable)
            ],
            check=True,
            capture_output=True,
            text=True
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_configured_edge_cases_pass(self):

        config = {
            "enabled": True,
            "cases": [
                {
                    "name": "both_zero",
                    "input": "0 0\n",
                    "expected_output": "0\n"
                },
                {
                    "name": "positive",
                    "input": "12 8\n",
                    "expected_output": "20\n"
                },
                {
                    "name": "negative",
                    "input": "-12 -8\n",
                    "expected_output": "-20\n"
                },
                {
                    "name": "mixed_signs",
                    "input": "-12 8\n",
                    "expected_output": "-4\n"
                },
                {
                    "name": "upper_boundary",
                    "input": "2147483647 0\n",
                    "expected_output": "2147483647\n"
                },
                {
                    "name": "lower_boundary",
                    "input": "-2147483648 0\n",
                    "expected_output": "-2147483648\n"
                }
            ]
        }

        result = check_logical(
            source_file=str(self.source),
            executable_path=str(self.executable),
            logical_config=config
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["passed_checks"], 6)
        self.assertEqual(result["total_checks"], 6)

    def test_wrong_expected_output_is_reported(self):

        config = {
            "enabled": True,
            "cases": [
                {
                    "name": "deliberate_mismatch",
                    "input": "2 3\n",
                    "expected_output": "99\n"
                }
            ]
        }

        result = check_logical(
            source_file=str(self.source),
            executable_path=str(self.executable),
            logical_config=config
        )

        self.assertEqual(result["status"], "FAIL")

        self.assertEqual(
            result["findings"][0]["expected_output"],
            "99\n"
        )

        self.assertEqual(
            result["findings"][0]["actual_output"].strip(),
            "5"
        )

    def test_disabled_metric(self):

        result = check_logical(
            executable_path=str(self.executable),
            logical_config={
                "enabled": False,
                "reason": "Not applicable."
            }
        )

        self.assertEqual(result["status"], "NOT_EVALUATED")

    def test_missing_cases_is_configuration_error(self):

        result = check_logical(
            executable_path=str(self.executable),
            logical_config={
                "enabled": True,
                "cases": []
            }
        )

        self.assertEqual(result["status"], "CONFIG_ERROR")

    def test_empty_input_and_expected_output_are_allowed_strings(self):

        result = check_logical(
            executable_path=str(self.executable),
            logical_config={
                "enabled": True,
                "cases": [
                    {
                        "name": "empty_input",
                        "input": "",
                        "expected_output": ""
                    }
                ]
            }
        )

        self.assertEqual(result["total_checks"], 1)
        self.assertEqual(result["status"], "FAIL")

    def test_result_is_json_serializable(self):

        result = check_logical(
            executable_path=str(self.executable),
            logical_config={
                "enabled": True,
                "cases": [
                    {
                        "name": "simple",
                        "input": "1 2\n",
                        "expected_output": "3\n"
                    }
                ]
            }
        )

        json.dumps(result)


if __name__ == "__main__":
    unittest.main()
