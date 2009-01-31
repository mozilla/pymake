SIMPLEVAR = aabb.cc

SIMPLE3SUBSTNAME = SIMPLEVAR:.dd
$(SIMPLE3SUBSTNAME) = weirdval

SIMPLESUBST = $(SIMPLEVAR:.cc=.dd)
SIMPLE2SUBST = $(SIMPLEVAR:.cc)
SIMPLE3SUBST = $(SIMPLEVAR:.dd)
PERCENTSUBST = $(SIMPLEVAR:%.cc=%.ee)
PERCENT2SUBST = $(SIMPLEVAR:aa%.cc=ff%.f)
PERCENT3SUBST = $(SIMPLEVAR:aa%.dd=gg%.gg)
PERCENT4SUBST = $(SIMPLEVAR:aa%.cc=gg)
PERCENT5SUBST = $(SIMPLEVAR:aa)

all:
	test "$(SIMPLESUBST)" = "aabb.dd"
	test "$(SIMPLE2SUBST)" = ""
	test "$(SIMPLE3SUBST)" = "weirdval"
	test "$(PERCENTSUBST)" = "aabb.ee"
	test "$(PERCENT2SUBST)" = "ffbb.f"
	test "$(PERCENT3SUBST)" = "aabb.cc"
	test "$(PERCENT4SUBST)" = "gg"
	test "$(PERCENT5SUBST)" = ""
	@echo TEST-PASS
