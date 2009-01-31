space = $(NULL) $(NULL)
hello$(space)world$(space) = hellovalue

VAR = value1\\
VAR2 = value2

all:
	test "$(hello world )" = "hellovalue"
	test "$(VAR)" = "value1\\"
	test "$(VAR2)" = "value2"
	@echo TEST-PASS
