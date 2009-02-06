ifdef FOO
$(error FOO is not defined!)
endif

FOO = foo
FOOFOUND = false
BARFOUND = false
BAZFOUND = false

ifdef FOO
FOOFOUND = true
else ifdef BAR
BARFOUND = true
else
BAZFOUND = true
endif

BAR2 = bar2
FOO2FOUND = false
BAR2FOUND = false
BAZ2FOUND = false

ifdef FOO2
FOO2FOUND = true
else ifdef BAR2
BAR2FOUND = true
else
BAZ2FOUND = true
endif

FOO3FOUND = false
BAR3FOUND = false
BAZ3FOUND = false

ifdef FOO3
FOO3FOUND = true
else ifdef BAR3
BAR3FOUND = true
else
BAZ3FOUND = true
endif

TESTEMPTY = $(NULL)
ifndef TESTEMPTY
$(error TEST-FAIL TESTEMPTY was probably expanded!)
endif

all:
	test $(FOOFOUND) = true   # FOOFOUND
	test $(BARFOUND) = false  # BARFOUND
	test $(BAZFOUND) = false  # BAZFOUND
	test $(FOO2FOUND) = false # FOO2FOUND
	test $(BAR2FOUND) = true  # BAR2FOUND
	test $(BAZ2FOUND) = false # BAZ2FOUND
	test $(FOO3FOUND) = false # FOO3FOUND
	test $(BAR3FOUND) = false # BAR3FOUND
	test $(BAZ3FOUND) = true  # BAZ3FOUND
ifneq ($(FOO),foo)
	echo TEST-FAIL 'FOO neq foo'
endif
ifneq ($(FOO), foo) # Whitespace after the comma is stripped
	echo TEST-FAIL 'FOO plus whitespace'
endif
ifeq ($(FOO), foo ) # But not trailing whitespace
	echo TEST-FAIL 'FOO plus trailing whitespace'
endif
ifeq ( $(FOO),foo) # Not whitespace after the paren
	echo TEST-FAIL 'FOO with leading whitespace'
endif
ifeq ($(FOO),$(NULL) foo) # Nor whitespace after expansion
	echo TEST-FAIL 'FOO with embedded ws'
endif
ifeq ($(BAR2),bar)
	echo TEST-FAIL 'BAR2 eq bar'
endif
ifeq '$(BAR3FOUND)' 'false'
	echo BAR3FOUND is ok
else
	echo TEST-FAIL BAR3FOUND is not ok
endif
ifndef FOO
	echo TEST-FAIL "foo not defined?"
endif
	@echo TEST-PASS
