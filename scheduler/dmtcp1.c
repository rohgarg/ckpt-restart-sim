#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>

#define TWO_GB 2500000000

int
main(int argc, char *argv[])
{
  int count = 1;

//  unsigned int TWO_GB = 2*1024*1024*1024;
  char *test = malloc(TWO_GB);
  memset(test, 0, TWO_GB);

  while (1) {
    printf(" %2d ", count++);
    fflush(stdout);
    sleep(2);
  }
  return 0;
}
