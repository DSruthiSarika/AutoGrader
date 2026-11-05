#include <stdio.h>

int binary_search(int n, int key) {
    int low = 0;
    int high = n - 1;

    while (low <= high) {
        int mid = low + (high - low) / 2;

        if (mid == key) {
            return mid;
        }

        if (mid < key) {
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }

    return -1;
}

int main() {
    int n, key;
    int repetitions = 1;

    if (scanf("%d %d", &n, &key) != 2 || n <= 0) {
        return 1;
    }

    /* Optional input used by complexity benchmarking. */
    scanf("%d", &repetitions);

    if (repetitions <= 0) {
        return 1;
    }

    volatile int result = -1;

    for (int i = 0; i < repetitions; i++) {
        result = binary_search(n, key);
    }

    printf("%d\n", result);

    return 0;
}