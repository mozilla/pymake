VAR = value

all:
	test "$( VAR)" = ""
	@echo TEST-PASS
