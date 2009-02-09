$(shell echo "INCLUDED2 = yes" >local-include.inc)

include $(TESTPATH)/include-file.inc local-include.inc

all:
	test "$(INCLUDED)" = "yes"
	@echo TEST-PASS
