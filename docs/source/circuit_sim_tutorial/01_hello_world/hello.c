/**
 * A program which prints Hello world into the "IO buffer" and exits.
 */

#include "sark.h"

void c_main(void)
{
  io_printf(IO_BUF, "Hello, world!\n");
}
