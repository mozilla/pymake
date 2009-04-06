#T gmake returncode: 2
#T pymake fail

includedeps $(TESTPATH)/includedeps.deps

all: file1

file1:
	touch $@
