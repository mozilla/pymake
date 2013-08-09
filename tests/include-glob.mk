include $(TESTPATH)/glob*.inc

ifeq ($A_$B,ok_ok)
all:
	@echo TEST-PASS
else
all:
	@echo TEST-FAIL
endif
