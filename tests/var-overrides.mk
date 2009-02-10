#T commandline: ['CLINEVAR=clineval', 'CLINEVAR2=clineval2']

# this doesn't actually test overrides yet, because they aren't implemented in pymake,
# but testing origins in general is important

MVAR = mval
CLINEVAR = deadbeef

all:
	test "$(origin NOVAR)" = "undefined"
	test "$(CLINEVAR)" = "clineval"
	test "$(origin CLINEVAR)" = "command line"
	test "$(MVAR)" = "mval"
	test "$(origin MVAR)" = "file"
	test "$(@)" = "all"
	test "$(origin @)" = "automatic"
	@echo TEST-PASS
