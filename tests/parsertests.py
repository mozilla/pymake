import pymake.data, pymake.parser, pymake.functions
import unittest
import logging

from cStringIO import StringIO

class TestBase(unittest.TestCase):
    def assertEqual(self, a, b, msg=""):
        """Actually print the values which weren't equal, if things don't work out!"""
        unittest.TestCase.assertEqual(self, a, b, "%s got %r expected %r" % (msg, a, b))

class DataTest(TestBase):
    testdata = (
        ((("He\tllo", "f", 1, 0),),
         ((0, "f", 1, 0), (2, "f", 1, 2), (3, "f", 1, 4))),
        ((("line1 ", "f", 1, 4), ("l\tine2", "f", 2, 11)),
         ((0, "f", 1, 4), (5, "f", 1, 9), (6, "f", 2, 11), (7, "f", 2, 12), (8, "f", 2, 16))),
    )

    def runTest(self):
        for datas, results in self.testdata:
            d = pymake.parser.Data(None, None)
            for line, file, lineno, col in datas:
                d.append(line, pymake.parser.Location(file, lineno, col))
            for pos, file, lineno, col in results:
                loc = d.getloc(pos)
                self.assertEqual(loc.path, file, "data file")
                self.assertEqual(loc.line, lineno, "data line")
                self.assertEqual(loc.column, col, "data %r col, got %i expected %i" % (d.data, loc.column, col))

class MakeSyntaxTest(TestBase):
    # (string, startat, stopat, stopoffset, expansion
    testdata = (
        ('hello world', 0, '', -1, ['hello world']),
        ('hello $W', 0, '', -1,
         ['hello ',
          {'type': 'VariableRef',
           '.vname': ['W']}
          ]),
        ('hello: world', 0, ':=', 5, ['hello']),
        ('h $(flavor FOO)', 0, '', -1,
         ['h ',
          {'type': 'FlavorFunction',
           '[0]': ['FOO']}
          ]),
        ('hello$$world', 0, '', -1, ['hello$world']),
        ('echo $(VAR)', 0, '', -1,
         ['echo ',
          {'type': 'VariableRef',
           '.vname': ['VAR']}
          ]),
        ('echo $($(VARNAME):.c=.o)', 0, '', -1,
         ['echo ',
          {'type': 'SubstitutionRef',
           '.vname': [{'type': 'VariableRef',
                       '.vname': ['VARNAME']}
                      ],
           '.substfrom': ['.c'],
           '.substto': ['.o']}
          ]),
        ('  $(VAR:VAL) = $(VAL)', 0, ':=', 13,
         ['  ',
          {'type': 'VariableRef',
           '.vname': ['VAR:VAL']},
          ' ']),
        ('  $(VAR:VAL) = $(VAL)', 15, '', -1,
         [{'type': 'VariableRef',
           '.vname': ['VAL']},
         ]),
    )

    def compareRecursive(self, actual, expected, path):
        self.assertEqual(len(actual), len(expected),
                         "compareRecursive: %s" % (path,))
        for i in xrange(0, len(actual)):
            ipath = path + [i]

            a = actual[i]
            e = expected[i]
            if isinstance(e, str):
                self.assertEqual(a, e, "compareRecursive: %s" % (ipath,))
            else:
                self.assertEqual(type(a), getattr(pymake.functions, e['type']),
                                 "compareRecursive: %s" % (ipath,))
                for k, v in e.iteritems():
                    if k == 'type':
                        pass
                    elif k[0] == '[':
                        item = int(k[1:-1])
                        proppath = ipath + [item]
                        self.compareRecursive(a[item], v, proppath)
                    elif k[0] == '.':
                        item = k[1:]
                        proppath = ipath + [item]
                        self.compareRecursive(getattr(a, item), v, proppath)
                    else:
                        raise Exception("Unexpected property at %s: %s" % (ipath, k))

    def runTest(self):
        for s, startat, stopat, stopoffset, expansion in self.testdata:
            d = pymake.parser.Data(None, None)
            d.append(s, pymake.parser.Location('testdata', 1, 0))

            a, stoppedat = pymake.parser.parsemakesyntax(d, startat, stopat, pymake.parser.PARSESTYLE_MAKEFILE)
            self.compareRecursive(a, expansion, [])
            self.assertEqual(stoppedat, stopoffset)

class VariableTest(TestBase):
    testdata = """
    VAR = value
    VARNAME = TESTVAR
    $(VARNAME) = testvalue
    $(VARNAME:VAR=VAL) = moretesting
    IMM := $(VARNAME) # this is a comment
    MULTIVAR = val1 \\
  val2
    VARNAME = newname
    """
    expected = {'VAR': 'value',
                'VARNAME': 'newname',
                'TESTVAR': 'testvalue',
                'TESTVAL': 'moretesting',
                'IMM': 'TESTVAR ',
                'MULTIVAR': 'val1 val2',
                'UNDEF': None}

    def runTest(self):
        m = pymake.data.Makefile()
        stream = StringIO(self.testdata)
        pymake.parser.parsestream(stream, 'testdata', m)
        for k, v in self.expected.iteritems():
            flavor, source, val = m.variables.get(k)
            if val is None:
                self.assertEqual(val, v, 'variable named %s' % k)
            else:
                self.assertEqual(val.resolve(m.variables, None), v, 'variable named %s' % k)

class SimpleRuleTest(TestBase):
    testdata = """
    VAR = value
TSPEC = dummy
all: TSPEC = myrule
all:: test test2 $(VAR)
	echo "Hello, $(TSPEC)"

%.o: %.c
	$(CC) -o $@ $<
"""

    def runTest(self):
        m = pymake.data.Makefile()
        stream = StringIO(self.testdata)
        pymake.parser.parsestream(stream, 'testdata', m)
        self.assertEqual(m.defaulttarget, 'all', "Default target")

        self.assertTrue(m.hastarget('all'), "Has 'all' target")
        target = m.gettarget('all')
        rules = target.rules
        self.assertEqual(len(rules), 1, "Number of rules")
        prereqs = rules[0].prerequisites
        self.assertEqual(prereqs, ['test', 'test2', 'value'], "Prerequisites")
        commands = rules[0].commands
        self.assertEqual(len(commands), 1, "Number of commands")
        expanded = commands[0].resolve(target.variables, None)
        self.assertEqual(expanded, 'echo "Hello, myrule"')

        irules = m.implicitrules
        self.assertEqual(len(irules), 1, "Number of implicit rules")

        irule = irules[0]
        self.assertEqual(len(irule.targetpatterns), 1, "%.o target pattern count")
        self.assertEqual(len(irule.prerequisites), 1, "%.o prerequisite count")
        self.assertEqual(irule.targetpatterns[0].match('foo.o'), 'foo', "%.o stem")
        self.assertEqual(irule.prerequisites[0].resolve(irule.targetpatterns[0].match('foo.o')), 'foo.c')

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
