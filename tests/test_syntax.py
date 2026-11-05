
import unittest
from pathlib import Path

from analyzers.syntax import check_syntax

ROOT = Path(__file__).resolve().parents[1]
SUBMISSIONS = ROOT / "submissions"


class TestSyntax(unittest.TestCase):

    def test_correct_submission_has_valid_syntax(self):
        result = check_syntax(
            str(SUBMISSIONS / "correct.c"),
            compiler="gcc",
            standard="c11",
            flags=["-Wall", "-Wextra", "-Werror"]
        )
        self.assertEqual(result.get("score"), 100)

    def test_compile_error_submission_fails_syntax_check(self):
        result = check_syntax(
            str(SUBMISSIONS / "compile_error.c"),
            compiler="gcc",
            standard="c11",
            flags=["-Wall", "-Wextra", "-Werror"]
        )
        self.assertEqual(result.get("score"), 0)


if __name__ == "__main__":
    unittest.main()
