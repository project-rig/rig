/**
 * A program which simply adds together two numbers in SDRAM and writes the
 * result striaght afterwards.
 */

#include <stdint.h>

#include "spin1_api.h"

void c_main(void)
{
  // Get the address of the allocated SDRAM block
  uint32_t *numbers = sark_tag_ptr(spin1_get_core_id(), 0);
  
  // Add the two numbers together and store the result back into SDRAM.
  numbers[2] = numbers[0] + numbers[1];
}
