#include <stdio.h>

#define BYTES_PER_LINE 32

void hexdump(FILE *fp) {
    unsigned char buffer[BYTES_PER_LINE];
    size_t n;
    unsigned long long addr = 0;
    int i;

    while ((n = fread(buffer, 1, BYTES_PER_LINE, fp)) > 0) {
        printf("%08llx  ", addr);
        for (i = 0; i < n; ++i) {
            printf("%02x ", buffer[i]);
            if (i == BYTES_PER_LINE/2-1)
                printf(" ");
        }

        if (n < BYTES_PER_LINE) {
            for (i = n; i < BYTES_PER_LINE; ++i) {
                printf("   ");
                if (i == BYTES_PER_LINE/2-1)
                    printf(" ");
            }
        }

        printf("  |");
        for (i = 0; i < n; ++i) {
            if (buffer[i] >= 32 && buffer[i] <= 126)
                printf("%c", buffer[i]);
            else
                printf(".");
        }
        printf("|\n");

        addr += n;
    }
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <file>\n", argv[0]);
        return 1;
    }

    FILE *fp = fopen(argv[1], "rb");
    if (fp == NULL) {
        perror("Unable to open file");
        return 1;
    }

    hexdump(fp);
    fclose(fp);

    return 0;
}
