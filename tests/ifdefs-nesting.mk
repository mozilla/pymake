ifdef RANDOM
ifeq (,$(error Not evaluated!))
VAR = val
endif
endif

all:
	@echo TEST-PASS
