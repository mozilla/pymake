unknown var = uval

all:
	test "$(subst a,b,value)" = "vblue"
	test "$( subst a,b,value)" = ""
	test "$(Subst a,b,value)" = ""
	test "$(unknown var)" = "uval"
	@echo TEST-PASS
