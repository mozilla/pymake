all:
	test "$(subst e,EE,hello)" = "hEEllo"
	test "$(strip $(NULL)  test data  )" = "test data"
	test "$(word 1, hello )" = "hello"
	test "$(word 2, hello )" = ""
	test "$(wordlist 1, 2, foo bar baz )" = "foo bar"
	@echo TEST-PASS
