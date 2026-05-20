export const SAMPLE_FILES = {
  "leaky.c": `#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main() {

    printf("=== PinTrace Leak Demo ===\n");

    // =====================================================
    // 1. malloc + proper free (NO LEAK)
    // =====================================================

    int *numbers = (int *)malloc(5 * sizeof(int));

    for (int i = 0; i < 5; i++) {
        numbers[i] = i * 10;
    }

    printf("numbers[2] = %d\n", numbers[2]);

    free(numbers);

    // =====================================================
    // 2. malloc WITHOUT free (LEAK)
    // =====================================================

    char *message = (char *)malloc(64);

    strcpy(message, "This malloc allocation is leaked.");

    printf("%s\n", message);

    // intentionally NOT freeing message

    // =====================================================
    // 3. calloc WITHOUT free (LEAK)
    // =====================================================

    double *values = (double *)calloc(8, sizeof(double));

    values[0] = 3.14159;
    values[1] = 2.71828;

    printf("values[0] = %.2f\n", values[0]);

    // intentionally NOT freeing values

    // =====================================================
    // 4. realloc + proper free (NO LEAK)
    // =====================================================

    int *buffer = (int *)malloc(3 * sizeof(int));

    buffer[0] = 1;
    buffer[1] = 2;
    buffer[2] = 3;

    buffer = (int *)realloc(buffer, 10 * sizeof(int));

    buffer[9] = 999;

    printf("buffer[9] = %d\n", buffer[9]);

    free(buffer);

    // =====================================================
    // 5. realloc WITHOUT final free (LEAK)
    // =====================================================

    char *text = (char *)malloc(16);

    strcpy(text, "Pin");

    text = (char *)realloc(text, 128);

    strcat(text, " Trace Memory Leak Demo");

    printf("%s\n", text);

    // intentionally NOT freeing text

    printf("=== Program Finished ===\n");

    return 0;

}
`
};

export const FILE_LANG = {
  "leaky.c": "c",
  "main.c": "c",
  "README.md": "markdown",
};
