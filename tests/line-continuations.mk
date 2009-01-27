SHELL = /Users/bsmedberg/bin/dump-args.py

VAR = val1 	 \
  	  val2  

all:
	test "$(VAR)" = "val1 val2  "
	test "hello \
	  world" = "hello   world"
	@echo TEST-PASS