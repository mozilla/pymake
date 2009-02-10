ifneq ($(strip $(MAKEFILE_LIST)),$(TESTPATH)/include-notfound.mk)
$(error MAKEFILE_LIST incorrect: '$(MAKEFILE_LIST)')
endif

-include notfound.inc-dummy

ifneq ($(strip $(MAKEFILE_LIST)),$(TESTPATH)/include-notfound.mk)
$(error MAKEFILE_LIST incorrect: '$(MAKEFILE_LIST)')
endif

all:
	@echo TEST-PASS

