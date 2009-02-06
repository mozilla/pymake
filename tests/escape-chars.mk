space = $(NULL) $(NULL)
hello$(space)world$(space) = hellovalue

A = aval

VAR = value1\\
VARAWFUL = value1\\#comment
VAR2 = value2
VAR3 = test\$A

EPERCENT = \%

all:
	test "$(hello world )" = "hellovalue"
	test "$(VAR)" = "value1\\"
	test '$(VARAWFUL)' = 'value1\'
	test "$(VAR2)" = "value2"
	test "$(VAR3)" = "test\aval"
	test "$(EPERCENT)" = "\%"
	@echo TEST-PASS
