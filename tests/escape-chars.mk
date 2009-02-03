space = $(NULL) $(NULL)
hello$(space)world$(space) = hellovalue

VAR = value1\\
VAR2 = value2

EPERCENT = \%

all:
	test "$(hello world )" = "hellovalue"
	test "$(VAR)" = "value1\\"
	test "$(VAR2)" = "value2"
	test "$(EPERCENT)" = "\%"
	@echo TEST-PASS
