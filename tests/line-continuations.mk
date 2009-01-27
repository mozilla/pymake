VAR = val1 	 \
  	  val2  

all:
	test "$(VAR)" = "val1 val2  "
	test "hello \
	  world" = "hello   world"
	test "hello" = \
"hello"
	@echo TEST-PASS