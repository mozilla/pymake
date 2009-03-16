all::
	sleep 1
	touch somefile

all:: somefile
	@echo TEST-PASS
