$(shell \
touch test.file; \
ln -s test.file test.symlink; \
)

all:
	test "$(abspath test.file)" = "$(CURDIR)/test.file"
	test "$(realpath test.symlink)" = "$(CURDIR)/test.file"
	@echo TEST-PASS
