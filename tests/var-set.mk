#T commandline: ['OBASIC=oval']

BASIC = val

TEST = $(TEST)

TEST2 = $(TES
TEST2 += T)

TES T = val

RECVAR = foo
RECVAR += var baz 

IMMVAR := bloo
IMMVAR += $(RECVAR)

all: BASIC = valall
all: RECVAR += $(BASIC)
all: IMMVAR += $(BASIC)
all: UNSET += more
all: OBASIC += allmore

RECVAR = blimey

all:
	test "$(TEST2)" = "val"
	test '$(value TEST2)' = '$$(TES T)'
	test "$(RECVAR)" = "blimey valall"
	test "$(IMMVAR)" = "bloo foo var baz  valall"
	test "$(UNSET)" = "more"
	test "$(OBASIC)" = "oval"
	@echo TEST-PASS
