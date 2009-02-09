TEST = $(TEST)

TEST2 = $(TES
TEST2 += T)

TES T = val

SETVAR = foo
SETVAR += var baz 

all: SETVAR += bam

all:
	test "$(TEST2)" = "val"
	test "$(SETVAR)" = "foo var baz  bam"
	test '$(value TEST2)' = '$$(TES T)'
	@echo TEST-PASS
