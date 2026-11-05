
import unittest
import tempfile
from pathlib import Path

from analyzers.modularity import check_modularity


class TestModularity(unittest.TestCase):

    def run_analyzer(self, code, config=None):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "test.c"
            source.write_text(code, encoding="utf-8")
            return check_modularity(str(source), config)

    def test_simple_program_gets_full_score(self):
        code = """
        int main() {
            return 0;
        }
        """
        result = self.run_analyzer(
            code,
            {"modularity": {"min_helper_functions": 0}}
        )
        self.assertEqual(result["score"], 100)

    def test_helper_function_detected(self):
        code = """
        void display() {
            return;
        }

        int main() {
            display();
            return 0;
        }
        """
        result = self.run_analyzer(code)
        self.assertEqual(result["score"], 100)
        self.assertIn("display", result["functions"])

    def test_missing_required_helper_function(self):
        code = """
        int main() {
            return 0;
        }
        """
        result = self.run_analyzer(
            code,
            {"modularity": {"min_helper_functions": 1}}
        )
        self.assertLess(result["score"], 100)
        self.assertEqual(result["status"], "REVIEW")

    def test_unused_helper_function(self):
        code = """
        void calculate() {
            return;
        }

        int main() {
            return 0;
        }
        """
        result = self.run_analyzer(
            code,
            {"modularity": {
                "min_helper_functions": 0,
                "require_helper_calls": True
            }}
        )
        self.assertLess(result["score"], 100)

    def test_invalid_configuration(self):
        code = "int main() { return 0; }"
        result = self.run_analyzer(
            code,
            {"modularity": {"min_helper_functions": -1}}
        )
        self.assertIsNone(result["score"])
        self.assertEqual(result["status"], "NOT_EVALUATED")


if __name__ == "__main__":
    unittest.main()
