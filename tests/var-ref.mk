VAR = value
VAR2 == value

all:
	test "$( VAR)" = ""
	test "$(VAR2)" = "= value"
	@echo TEST-PASS
