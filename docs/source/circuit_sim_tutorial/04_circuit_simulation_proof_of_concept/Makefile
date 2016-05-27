APPS := gate
APPS += stimulus
APPS += probe

MAKEFILE := $(SPINN_DIRS)/make/app.make

all: $(DIRS)
	for app in $(APPS); do ("$(MAKE)" -f "$(MAKEFILE)" APP=$$app) || exit $$?; done

clean: $(DIRS)
	for app in $(APPS); do ("$(MAKE)" -f "$(MAKEFILE)" APP=$$app clean) || exit $$?; done
