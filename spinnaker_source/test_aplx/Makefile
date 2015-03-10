APP = rig_test
APP_OUTPUT_DIR = ../../rig/binaries/
BUILD_DIR = build

OBJECTS = test.o
LIBRARIES = -lspin1_api

include $(SPINN_DIRS)/Makefile.common

all: $(APP_OUTPUT_DIR)$(APP).aplx

clean:
	$(RM) $(OBJECTS) $(BUILD_DIR)$(APP).elf $(BUILD_DIR)$(APP).txt $(APP_OUTPUT_DIR)$(APP).aplx
