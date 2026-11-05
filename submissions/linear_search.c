
#include <stdio.h>
#include <stdlib.h>

int linear_search(int arr[], int n, int key) {
    for (int i = 0; i < n; i++) {
        if (arr[i] == key) {
            return i;
        }
    }
    return -1;
}

int main() {
    int n, key;

    if (scanf("%d", &n) != 1 || n <= 0) {
        return 1;
    }

    int *arr = malloc(n * sizeof(int));

    if (arr == NULL) {
        return 1;
    }

    for (int i = 0; i < n; i++) {
        arr[i] = i;
    }

    if (scanf("%d", &key) != 1) {
        free(arr);
        return 1;
    }

    int result = linear_search(arr, n, key);

    printf("%d\n", result);

    free(arr);
    return 0;
}
