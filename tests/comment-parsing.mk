# where do comments take effect?

VAR = val1 # comment
VAR2 = literal\#hash
VAR3 = val3
VAR4 = literal\\#backslash
VAR5 = literal\char
# This comment extends to the next line \
VAR3 = ignored

all:
	test "$(VAR)" = "val1 "
	test "$(VAR2)" = "literal#hash"
	test "$(VAR3)" = "val3"
	test '$(VAR4)' = 'literal\'
	test '$(VAR5)' = 'literal\char'
	@echo "TEST-PASS"
