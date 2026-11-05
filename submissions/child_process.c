#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(void) {
    pid_t pid = fork();

    if (pid < 0) {
        return 1;
    }

    if (pid == 0) {
        while (1) {
            sleep(1);
        }
    }

    printf("Child PID: %d\n", pid);
    fflush(stdout);

    while (1) {
        sleep(1);
    }

    return 0;
}