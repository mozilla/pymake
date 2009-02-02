all:
	test "$(patsubst foo,%.bar,foo)" = "%.bar"
	@echo TEST-PASS
