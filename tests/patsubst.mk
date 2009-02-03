all:
	test "$(patsubst foo,%.bar,foo)" = "%.bar"
	test "$(patsubst \%word,replace,word %word other)" = "word replace other"
	test "$(patsubst %.c,\%%.o,foo.c bar.o baz.cpp)" = "%foo.o bar.o baz.cpp"
	@echo TEST-PASS
