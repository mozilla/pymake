all:
	test "$(subst e,EE,hello)" = "hEEllo"
	test "$(strip $(NULL)  test data  )" = "test data"
	test "$(word 1, hello )" = "hello"
	test "$(word 2, hello )" = ""
	test "$(wordlist 1, 2, foo bar baz )" = "foo bar"
	test "$(words 1 2 3)" = "3"
	test "$(words )" = "0"
	test "$(firstword $(NULL) foo bar baz)" = "foo"
	test "$(firstword )" = ""
	test "$(dir foo.c path/foo.o dir/dir2/)" = "./ path/ dir/dir2/"
	test "$(notdir foo.c path/foo.o dir/dir2/)" = "foo.c foo.o "
	@echo TEST-PASS
