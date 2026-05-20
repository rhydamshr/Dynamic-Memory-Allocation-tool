#include <stdio.h>
#include <stdlib.h>

int main() {
    // First allocation
    int *a = (int *)malloc(5 * sizeof(int));

    // Second allocation
    int *b = (int *)malloc(10 * sizeof(int));

    // Use the memory
    a[0] = 42;
    b[0] = 99;

    printf("a[0] = %d\n", a[0]);
    printf("b[0] = %d\n", b[0]);

    // Free only one allocation
    free(a);

    // b is never freed -> MEMORY LEAK

    return 0;
}