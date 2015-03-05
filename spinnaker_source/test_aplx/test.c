#include <stdint.h>
#include "spin1_api.h"
#include "sark.h"

void c_main(void)
{
  // Write to a word in SDRAM to indicate that we loaded correctly.
  uint32_t *sdram_base = (uint32_t *)sv->sdram_base;

  io_printf(IO_BUF, "Writing to SDRAM (0x%08x + %d).\n",
            sdram_base, sark_core_id());

  sdram_base[sark_core_id()] = (sark_chip_id() << 16 | sark_core_id());
}
