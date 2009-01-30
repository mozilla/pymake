space = $(NULL) $(NULL)
hello$(space)world$(space) = hellovalue

all:
	test "$(hello world )" = "hellovalue"
	@echo TEST-PASS