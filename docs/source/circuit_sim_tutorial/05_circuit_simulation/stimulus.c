/**
 * A stimulus generator which outputs a sequence of values provided by the
 * host.
 */

#include <stdint.h>
#include "spin1_api.h"

/**
 * Definition of the configuration data block written by the host to define the
 * stimulus kernel's behaviour.
 */
typedef struct {
	// The number of milliseconds to run for
	uint32_t sim_length;
	
	// The routing key to use when transmitting the output value
	uint32_t output_key;
	
	// An array of ceil(sim_length/8) bytes where bit-0 of byte[0] contains the first
	// bit to send, bit-1 gives the second bit and bit-0 of byte[1] gives the
	// eighth bit and so on...
	uint8_t stimulus[];
} config_t;


// A pointer to the configuration data loaded by the host into SDRAM.
config_t *config;


/**
 * Timer callback function, called once per millisecond.
 *
 * Looks-up and transmits the next output value in the stimulus.
 */
void on_tick(uint32_t ticks, uint32_t arg1) {
	// The tick count provided by Spin1 API starts from 1 so decrement to get a
	// 0-indexed count.
	ticks--;
	
	// Terminate after the specified number of ticks.
	if (ticks >= config->sim_length) {
		spin1_exit(0);
		return;
	}
	
	// Get the next output value
	uint32_t output = (config->stimulus[ticks / 8] >> (ticks % 8)) & 1;
	
	// Send the new output value as the payload in a multicast packet.
	spin1_send_mc_packet(config->output_key, output, WITH_PAYLOAD);
}


void c_main(void) {
	// Find the configuration data for this core.
	config = sark_tag_ptr(spin1_get_core_id(), 0);
	
	// Set up the timer to call on_tick() every millisecond
	spin1_set_timer_tick(1000); // 1ms
	spin1_callback_on(TIMER_TICK, on_tick, 1);
	
	// Start the Spin1 API event loop.
	// Waits for the "sync0" signal to arrive and then run the application
	// until it is terminated by spin1_exit().
	spin1_start(SYNC_WAIT);
}
