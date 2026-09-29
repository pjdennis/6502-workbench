#include <stdio.h>

int main() {
  int c;
  int col = 1;
  const int max_col = 4;
  while ((c = getchar()) != EOF) {
    if (c == '\n') {
      if (col < max_col) {
        putchar(' '); putchar(' ');
        col++;
      } else {
        putchar('\n');
	col = 1;
      }
    } else {
      putchar(c);
    }
  }
  if (col != 1) {
    putchar('\n');
  }

  return 0;
}
