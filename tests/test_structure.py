
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analyzers.structure import check_structure

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "submissions" / "correct.c"


class TestStructure(unittest.TestCase):

    def test_structure_returns_valid_score(self):
        result = check_structure(
            str(SOURCE),
            max_cyclomatic=8,
            max_function_length=40,
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("metric"), "structure")

        if result.get("score") is not None:
            self.assertIsInstance(
                result["score"],
                (int, float)
            )
            self.assertGreaterEqual(result["score"], 0)
            self.assertLessEqual(result["score"], 100)

    def test_lizard_fallback_detects_functions(self):
        source_code = """
#include <stdio.h>

int add(int a, int b) {
    return a + b;
}

int main(void) {
    printf("%d\\n", add(2, 3));
    return 0;
}
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "fallback_test.c"
            source.write_text(source_code)

            with patch("analyzers.structure.lizard", None):
                with patch(
                    "analyzers.structure.shutil.which",
                    return_value=None
                ):
                    result = check_structure(str(source))

        self.assertEqual(result.get("status"), "HEURISTIC_FALLBACK")
        self.assertIsNone(result.get("score"))
        self.assertEqual(len(result.get("functions", [])), 2)

    def test_cppcheck_runs_when_lizard_is_unavailable(self):
        source_code = """
int main(void) {
    return 0;
}
"""

        fake_cppcheck_result = subprocess.CompletedProcess(
            args=["cppcheck"],
            returncode=0,
            stdout="",
            stderr="",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "fallback_test.c"
            source.write_text(source_code)

            with patch("analyzers.structure.lizard", None):
                with patch(
                    "analyzers.structure.shutil.which",
                    return_value="/fake/cppcheck"
                ):
                    with patch(
                        "analyzers.structure.subprocess.run",
                        return_value=fake_cppcheck_result
                    ) as mock_run:

                        result = check_structure(str(source))

        self.assertTrue(result["cppcheck"]["available"])
        self.assertEqual(
            result["cppcheck"]["status"],
            "COMPLETED"
        )
        mock_run.assert_called_once()

    def test_cppcheck_unavailable_does_not_break_fallback(self):
        source_code = """
int main(void) {
    return 0;
}
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "fallback_test.c"
            source.write_text(source_code)

            with patch("analyzers.structure.lizard", None):
                with patch(
                    "analyzers.structure.shutil.which",
                    return_value=None
                ):
                    result = check_structure(str(source))

        self.assertEqual(
            result.get("status"),
            "HEURISTIC_FALLBACK"
        )
        self.assertIsNone(result.get("score"))
        self.assertFalse(result["cppcheck"]["available"])


if __name__ == "__main__":
    unittest.main()
