#include <stdint.h>
#include "spin1_api.h"
#include "sark.h"


void user_event(uint32_t arg0, uint32_t arg1)
{
  // On a user write the core_id and x, y co-ordinates in the reverse order.
  uint32_t *sdram_base = (uint32_t *)sv->sdram_base;
  io_printf(IO_BUF, "Writing to SDRAM (0x%08x + %d).\n",
            sdram_base, sark_core_id() * 4);
  sdram_base[sark_core_id()] = (sark_core_id() << 16 | sark_chip_id());
}

void c_main(void)
{
  // Write to a word in SDRAM to indicate that we loaded correctly.
  uint32_t *sdram_base = (uint32_t *)sv->sdram_base;
  io_printf(IO_BUF, "Writing to SDRAM (0x%08x + %d).\n",
            sdram_base, sark_core_id() * 4);
  sdram_base[sark_core_id()] = (sark_chip_id() << 16 | sark_core_id());

  spin1_callback_on(USER_EVENT, user_event, 0);
  spin1_start(SYNC_NOWAIT);
}
