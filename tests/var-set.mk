TEST = $(TEST)

TEST2 = $(TES
TEST2 += T)

TES T = val

SETVAR = foo
SETVAR += var baz 

all:
	test "$(TEST2)" = "val"
	test "$(SETVAR)" = "foo var baz "
	@echo TEST-PASS
