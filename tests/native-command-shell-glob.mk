#T gmake skip
all:
	mkdir shell-glob-test
	touch shell-glob-test/foo.txt
	touch shell-glob-test/bar.txt
	$(RM) shell-glob-test/*.txt
	$(RM) -r shell-glob-test
	@echo TEST-PASS