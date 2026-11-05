
import tempfile
import unittest
from pathlib import Path

from analyzers.memory_safety import check_memory_safety


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "submissions" / "correct.c"


class TestMemorySafety(unittest.TestCase):

    def run_analyzer(self, source_code, test_inputs=None):
        """Create a temporary C program and run the memory analyzer."""

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "test_program.c"
            source.write_text(source_code)

            return check_memory_safety(
                str(source),
                test_inputs=test_inputs or [""],
                timeout_seconds=3,
            )

    def test_memory_safety_analyzer_returns_result(self):
        """Verify the analyzer works with an existing submission."""

        result = check_memory_safety(
            str(SOURCE),
            test_inputs=["5 7\n", "0 0\n", "-1 1\n"],
            timeout_seconds=2,
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("metric"), "memory_safety")
        self.assertIn("status", result)

    def test_buffer_overflow_is_detected(self):
        """Verify AddressSanitizer detects a heap buffer overflow."""

        source_code = r"""
#include <stdlib.h>

int main(void) {
    int *arr = malloc(2 * sizeof(int));

    if (arr == NULL) {
        return 1;
    }

    arr[2] = 100;

    free(arr);
    return 0;
}
"""

        result = self.run_analyzer(source_code)

        self.assertEqual(result.get("status"), "SANITIZER_ISSUE")
        self.assertEqual(result.get("score"), 0)

    def test_use_after_free_is_detected(self):
        """Verify AddressSanitizer detects heap-use-after-free."""

        source_code = r"""
#include <stdlib.h>

int main(void) {
    int *ptr = malloc(sizeof(int));

    if (ptr == NULL) {
        return 1;
    }

    *ptr = 10;
    free(ptr);

    return *ptr;
}
"""

        result = self.run_analyzer(source_code)

        self.assertEqual(result.get("status"), "SANITIZER_ISSUE")
        self.assertEqual(result.get("score"), 0)

    def test_memory_leak_detection_limitation(self):
        """
        Verify the analyzer handles a leaking program.

        LeakSanitizer is unsupported in the current Apple Clang
        environment, so this test does not expect leak detection.
        """

        source_code = r"""
#include <stdlib.h>

int main(void) {
    int *ptr = malloc(100 * sizeof(int));

    if (ptr == NULL) {
        return 1;
    }

    ptr[0] = 10;

    return 0;
}
"""

        result = self.run_analyzer(source_code)

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("metric"), "memory_safety")
        self.assertIn("status", result)

    def test_safe_program_has_no_detected_issue(self):
        """Verify a program with valid allocation and deallocation."""

        source_code = r"""
#include <stdlib.h>

int main(void) {
    int *ptr = malloc(5 * sizeof(int));

    if (ptr == NULL) {
        return 1;
    }

    ptr[0] = 10;
    free(ptr);

    return 0;
}
"""

        result = self.run_analyzer(source_code)

        self.assertEqual(
            result.get("status"),
            "NO_ISSUE_DETECTED"
        )
        self.assertEqual(result.get("score"), 100)


if __name__ == "__main__":
    unittest.main()
