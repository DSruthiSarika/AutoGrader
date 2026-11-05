
import unittest
from pathlib import Path

from analyzers.originality import check_originality

ROOT = Path(__file__).resolve().parents[1]
SUBMISSIONS = ROOT / "submissions"


class TestOriginality(unittest.TestCase):

    def test_originality_compares_other_submissions(self):
        source = SUBMISSIONS / "correct.c"
        comparison_files = [
            path
            for path in SUBMISSIONS.glob("*.c")
            if path.resolve() != source.resolve()
        ]

        result = check_originality(
            source_file=source,
            comparison_files=comparison_files,
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("metric"), "originality")
        self.assertIsInstance(result.get("score"), (int, float))
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)
        self.assertIn("comparisons", result)


if __name__ == "__main__":
    unittest.main()

