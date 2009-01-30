#T returncode: 2

all:
	test "$(TESTVAR)" = "testval"

TESTVAR = testval\