
import unittest
import tempfile
from pathlib import Path

from analyzers.complexity import check_complexity


class TestComplexity(unittest.TestCase):

    def test_linear_program_returns_valid_result(self):
        source_code = r"""
        #include <stdio.h>

        int main() {
            int n;
            long long sum = 0;

            if (scanf("%d", &n) != 1 || n < 0) {
                return 1;
            }

            for (int i = 0; i < n; i++) {
                sum += i;
            }

            printf("%lld\n", sum);
            return 0;
        }
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "linear.c"
            source_file.write_text(source_code, encoding="utf-8")

            result = check_complexity(
                str(source_file),
                benchmark_cases=[
                    {"input_size": 1000, "input": "1000\n"},
                    {"input_size": 2000, "input": "2000\n"},
                    {"input_size": 4000, "input": "4000\n"},
                    {"input_size": 8000, "input": "8000\n"},
                ],
                timeout_seconds=3,
                repetitions=3,
            )

        self.assertEqual(result.get("metric"), "complexity")
        self.assertEqual(len(result.get("measurements", [])), 4)

        for measurement in result["measurements"]:
            self.assertEqual(measurement["runs_completed"], 3)
            self.assertIsNotNone(measurement["median_seconds"])

    def test_constant_time_program(self):
        source_code = r"""
        #include <stdio.h>

        int main() {
            int n;

            if (scanf("%d", &n) != 1) {
                return 1;
            }

            printf("%d\n", n + 1);
            return 0;
        }
        """

        self._run_benchmark(source_code)

    def test_logarithmic_time_program(self):
        source_code = r"""
        #include <stdio.h>

        int main() {
            int n;

            if (scanf("%d", &n) != 1 || n < 1) {
                return 1;
            }

            int count = 0;

            while (n > 1) {
                n /= 2;
                count++;
            }

            printf("%d\n", count);
            return 0;
        }
        """

        self._run_benchmark(source_code)

    def test_quadratic_time_program(self):
        source_code = r"""
        #include <stdio.h>

        int main() {
            int n;

            if (scanf("%d", &n) != 1 || n < 0) {
                return 1;
            }

            volatile long long count = 0;

            for (int i = 0; i < n; i++) {
                for (int j = 0; j < n; j++) {
                    count++;
                }
            }

            printf("%lld\n", count);
            return 0;
        }
        """

        self._run_benchmark(source_code)

    def _run_benchmark(self, source_code):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "benchmark.c"
            source_file.write_text(source_code, encoding="utf-8")

            result = check_complexity(
                str(source_file),
                benchmark_cases=[
                    {"input_size": 1000, "input": "1000\n"},
                    {"input_size": 2000, "input": "2000\n"},
                    {"input_size": 4000, "input": "4000\n"},
                    {"input_size": 8000, "input": "8000\n"},
                ],
                timeout_seconds=3,
                repetitions=3,
            )

        self.assertEqual(result.get("metric"), "complexity")
        self.assertEqual(len(result.get("measurements", [])), 4)

        for measurement in result["measurements"]:
            self.assertEqual(measurement["runs_completed"], 3)
            self.assertIsNotNone(measurement["median_seconds"])


if __name__ == "__main__":
    unittest.main()
