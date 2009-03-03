ifdef .PYMAKE
TOUCH = %pymake.builtins touch
else
TOUCH = touch
endif

all: testfile
	test -f testfile
	@echo TEST-PASS

testfile:
	$(TOUCH) $@
