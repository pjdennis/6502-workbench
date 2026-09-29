#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
  if (argc != 4) {
    fprintf(stderr, "usage zeros <count in hex> <infile> <outfile>\n");
    return 1;
  }

  long zeros = strtol(argv[1], NULL, 16);
  char* infilename = argv[2];
  char* outfilename = argv[3];

  FILE* in_file_p = fopen(infilename, "rb");

  if (!in_file_p) {
    fprintf(stderr, "unable to open input file: %s\n", infilename);
    return 1;
  }

  FILE* out_file_p = fopen(outfilename, "wb");
  if (!out_file_p) {
    fprintf(stderr, "unable to create output file: %s\n", outfilename);
    fclose(in_file_p);
    return 1;
  }

  for (long x = 0; x != zeros; x++) {
    fputc(0, out_file_p);
  }

  int c;
  while ((c = fgetc(in_file_p)) != EOF) {
    fputc(c, out_file_p);
  }

  fclose(out_file_p);
  fclose(in_file_p);

  return 0;
}
