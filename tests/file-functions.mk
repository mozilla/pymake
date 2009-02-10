$(shell \
touch test.file; \
ln -s test.file test.symlink; \
touch .testhidden; \
mkdir foo; \
touch foo/testfile; \
)

all:
	test "$(abspath test.file test.symlink)" = "$(CURDIR)/test.file $(CURDIR)/test.symlink"
	test "$(realpath test.file test.symlink)" = "$(CURDIR)/test.file $(CURDIR)/test.file"
	test "$(sort $(wildcard *))" = "foo test.file test.symlink"
# commented out because GNU make matches . and .. while python doesn't, and I don't
# care enough
#	test "$(sort $(wildcard .*))" = ". .. .testhidden"
	test "$(sort $(wildcard test*))" = "test.file test.symlink"
	test "$(sort $(wildcard foo/*))" = "foo/testfile"
	test "$(sort $(wildcard ./*))" = "./foo ./test.file ./test.symlink"
	test "$(sort $(wildcard f?o/*))" = "foo/testfile"
	@echo TEST-PASS
