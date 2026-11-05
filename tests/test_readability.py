

import unittest
from pathlib import Path

from analyzers.readability import check_readability

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "submissions" / "correct.c"


class TestReadability(unittest.TestCase):

    def test_readability_returns_valid_score(self):
        result = check_readability(SOURCE)

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("metric"), "readability")
        self.assertIsInstance(result.get("score"), (int, float))
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)


if __name__ == "__main__":
    unittest.main()


