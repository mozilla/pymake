# where do comments take effect?

VAR = val1 # comment
VAR2 = literal\#hash
VAR3 = val3
# This comment extends to the next line \
VAR3 = ignored

all:
	test "$(VAR)" = "val1 "
	test "$(VAR2)" = "literal#hash"
	test "$(VAR3)" = "val3"
	@echo "TEST-PASS"
