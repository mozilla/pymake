VAR = val1 	 \
  	  val2  

VAR2 = val1space\
val2

all:
	test "$(VAR)" = "val1 val2  "
	test "$(VAR2)" = "val1space val2"
	test "hello \
	  world" = "hello   world"
	test "hello" = \
"hello"
	@echo TEST-PASS
