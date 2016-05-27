/**
 * A generic (lookup-table based) logic gate simulating application kernel.
 */

#include <stdint.h>
#include "spin1_api.h"

/**
 * Definition of the configuration data block written by the host to configure
 * the gate's behaviour.
 */
typedef struct {
	// The number of milliseconds to run for
	uint32_t sim_length;
	
	// The routing key used by multicast packets relating to input a
	uint32_t input_a_key;
	
	// The routing key used by multicast packets relating to input b
	uint32_t input_b_key;
	
	// The routing key to use when transmitting the output value
	uint32_t output_key;
	
	// A lookup table from input a and b to output value.
	//
	// =======  =======  ==============
	// input a  input b  lut bit number
	// =======  =======  ==============
	// 0        0        0
	// 1        0        1
	// 0        1        2
	// 1        1        3
	// =======  =======  ==============
	uint32_t lut;
} config_t;


// A pointer to the configuration data loaded by the host into SDRAM.
config_t *config;

// The most recently received values for the two inputs
uint32_t last_input_a;
uint32_t last_input_b;


/**
 * Timer callback function, called once per millisecond.
 *
 * Looks-up and transmits the current output value for the gate being
 * simulated.
 */
void on_tick(uint32_t ticks, uint32_t arg1) {
	// Terminate after the specified number of ticks.
	// NB: the tick count starts from 1!
	if (ticks > config->sim_length) {
		spin1_exit(0);
		return;
	}
	
	// Look-up the new output value
	uint32_t lut_bit_number = last_input_a | (last_input_b << 1);
	uint32_t output = (config->lut >> lut_bit_number) & 1;
	
	// Send the output value of the simulated gate as the payload in a
	// multicast packet.
	spin1_send_mc_packet(config->output_key, output, WITH_PAYLOAD);
}

/**
 * Callback called when a multicast packet arrives with an input value.
 *
 * Remember the last input value received. The specific input a value is sent
 * to is indicated by its routing key.
 */
void on_mc_packet(uint32_t key, uint32_t payload) {
	if (key == config->input_a_key)
		last_input_a = payload;
	if (key == config->input_b_key)
		last_input_b = payload;
}


void c_main(void) {
	// Find the configuration data for this core.
	config = sark_tag_ptr(spin1_get_core_id(), 0);
	
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

