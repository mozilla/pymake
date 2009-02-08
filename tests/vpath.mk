VPATH = foo bar

$(shell \
mkdir foo; touch foo/tfile1; \
mkdir bar; touch bar/tfile2 bar/test.objtest; \
sleep 1; \
touch bar/test.source)

all: tfile1 tfile2 test.objtest test.source
	test "$^" = "foo/tfile1 bar/tfile2 test.objtest bar/test.source"
	@echo TEST-PASS

%.objtest: %.source
	test "$<" = bar/test.source
	test "$@" = test.objtest
