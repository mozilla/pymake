VPATH = foo bar

$(shell mkdir foo; touch foo/tfile1; mkdir bar; touch bar/tfile2)

all: tfile1 tfile2
	test "$^" = "foo/tfile1 bar/tfile2"
	@echo TEST-PASS
