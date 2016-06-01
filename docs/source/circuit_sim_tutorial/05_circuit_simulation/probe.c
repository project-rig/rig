/**
 * A probe which records the value of an incoming signal every millisecond.
 */

#include <stdint.h>
#include "spin1_api.h"

/**
 * Definition of the configuration data block written by the host to define the
 * probe's behaviour.
 */
typedef struct {
	// The number of milliseconds to run for
	uint32_t sim_length;
	
	// The routing key used by multicast packets relating to the probed input
	uint32_t input_key;
	
	// An array of ceil(sim_length/8) bytes where bit-0 of byte[0] will be
	// written with value in the first millisecond, bit-1 gives the value in the
	// second millisecond and bit-0 of byte[1] gives the value in the eighth
	// millisecond and so on...
	uchar recording[];
} config_t;


// A pointer to the configuration data loaded by the host into SDRAM.
config_t *config;

// The most recently received value
uint32_t last_input = 0;


/**
 * Timer callback function, called once per millisecond.
 *
 * Stores the most recently received value into memory.
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
	
	// Pause for a while to allow values sent during this millisecond to arrive
	// at this core.
	spin1_delay_us(700);
	
	// Record the most recently received value into memory
	config->recording[ticks/8] |= last_input << (ticks % 8);
}

/**
 * Callback called when a multicast packet arrives with an input value.
 *
 * Remembers the last input value received.
 */
void on_mc_packet(uint32_t key, uint32_t payload) {
	if (key == config->input_key)
		last_input = payload;
}


void c_main(void) {
	// Find the configuration data for this core.
	config = sark_tag_ptr(spin1_get_core_id(), 0);
	
	// Zero-out the recording area allocated by the host.
	for (int i = 0; i < (config->sim_length + 7)/8; i++)
		config->recording[i] = 0;
	
	// Set up the timer to call on_tick() every millisecond
	spin1_set_timer_tick(1000); // 1ms
	spin1_callback_on(TIMER_TICK, on_tick, 1);
	
	// Set up on_mc_packet() as a callback whenever a multicast packet arrives
	spin1_callback_on(MCPL_PACKET_RECEIVED, on_mc_packet, -1);
	
	// Start the Spin1 API event loop.
	// Waits for the "sync0" signal to arrive and then run the application
	// until it is terminated by spin1_exit().
	spin1_start(SYNC_WAIT);
}
