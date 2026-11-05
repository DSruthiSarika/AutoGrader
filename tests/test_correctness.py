
import unittest
from pathlib import Path

from agent.compiler import compile_c_program
from analyzers.correctness import (
    check_correctness,
    normalize_output,
)

ROOT = Path(__file__).resolve().parents[1]
TEST_FILE = ROOT / "tests" / "addition_tests.json"


class TestCorrectness(unittest.TestCase):

    def check_submission(self, filename):
        source = ROOT / "submissions" / filename
        compilation = compile_c_program(str(source))

        self.assertTrue(
            compilation.get("success"),
            f"Compilation failed: {compilation.get('error')}"
        )

        executable = compilation.get("executable")
        self.assertTrue(executable)

        try:
            return check_correctness(
                executable,
                str(TEST_FILE),
                2
            )
        finally:
            try:
                Path(executable).unlink(missing_ok=True)
            except OSError:
                pass

    def test_correct_submission_passes(self):
        result = self.check_submission("correct.c")
        self.assertEqual(result.get("score"), 100)

    def test_wrong_output_submission_fails(self):
        result = self.check_submission("wrong_output.c")
        self.assertLess(result.get("score", 100), 100)

    def test_trailing_whitespace_is_ignored(self):
        self.assertEqual(
            normalize_output("Hello World\n"),
            normalize_output("Hello World")
        )

    def test_multiple_internal_spaces_are_preserved(self):
        self.assertNotEqual(
            normalize_output("Hello  World"),
            normalize_output("Hello World")
        )

    def test_missing_internal_space_is_detected(self):
        self.assertNotEqual(
            normalize_output("HelloWorld"),
            normalize_output("Hello World")
        )

    def test_multiline_output_is_preserved(self):
        self.assertNotEqual(
            normalize_output("Hello\nWorld"),
            normalize_output("Hello World")
        )

    def test_empty_output(self):
        self.assertEqual(normalize_output(""), "")

    def test_leading_and_trailing_whitespace_is_ignored(self):
        self.assertEqual(
            normalize_output("  Hello World  \n"),
            normalize_output("Hello World")
        )


if __name__ == "__main__":
    unittest.main()
