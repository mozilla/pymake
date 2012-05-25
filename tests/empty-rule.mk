all: obj
	$(MAKE) -f $(word $(words $(MAKEFILE_LIST)),$(MAKEFILE_LIST)) obj

obj: header
	if [ -e obj ]; then echo TEST-FAIL; fi;
	touch obj

header: cpp

cpp:
	touch header
	touch cpp
