#T gmake skip

$(shell touch filemissing)

all: file1
	@echo TEST-PASS

includedeps $(TESTPATH)/includedeps.deps

file:
	@echo TEST-FAIL
