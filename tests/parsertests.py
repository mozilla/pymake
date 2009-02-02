import pymake.parser
import pymake.data
import unittest
import logging

class TestBase(unittest.TestCase):
    def assertEqual(self, a, b, msg=""):
        """Actually print the values which weren't equal, if things don't work out!"""
        unittest.TestCase.assertEqual(self, a, b, "%s got %r expected %r" % (msg, a, b))

class FindCommentTest(TestBase):
    testdata = (
        ("Hello # Comment", 6),
        ("# Line comment", 0),
        ("No comment", -1),
    )

    def runTest(self):
        for line, expected in self.testdata:
            self.assertEqual(pymake.parser.findcommenthash(line), expected,
                             "findcommenthash: %r" % (line,) )

class IsContinuationTest(TestBase):
    testdata = (
        ("Hello", False),
        ("Hello \\", False),
        ("Hello \\\n", True),
        ("Hello \\\\", False),
        ("Hello \\\\\n", False),
    )

    def runTest(self):
        for line, expected in self.testdata:
            self.assertEqual(pymake.parser.iscontinuation(line), expected,
                             "iscontinuation: %r" % (line,) )

class LStripCountTest(TestBase):
    testdata = (
        ("Hello", 0, "Hello"),
        ("  Hello", 2, "Hello"),
        ("\tHello", 4, "Hello"),
        ("\t  Hello  ", 6, "Hello  "),
    )

    def runTest(self):
        for line, col, result in self.testdata:
            aresult, acol = pymake.parser.lstripcount(line)
            self.assertEqual(acol, col, "lstripcount column: %r" % (line,))
            self.assertEqual(aresult, result, "lstripcount result: %r" % (line,))

class DataTest(TestBase):
    testdata = (
        ((("He\tllo", "f", 1, 0),),
         ((0, "f", 1, 0), (2, "f", 1, 2), (3, "f", 1, 4))),
        ((("line1 ", "f", 1, 4), ("l\tine2", "f", 2, 11)),
         ((0, "f", 1, 4), (5, "f", 1, 9), (6, "f", 2, 11), (7, "f", 2, 12), (8, "f", 2, 16))),
    )

    def runTest(self):
        for datas, results in self.testdata:
            d = pymake.parser.Data()
            for line, file, lineno, col in datas:
                d.append(line, pymake.parser.Location(file, lineno, col))
            for pos, file, lineno, col in results:
                loc = d.getloc(pos)
                self.assertEqual(loc.path, file, "data file")
                self.assertEqual(loc.line, lineno, "data line")
                self.assertEqual(loc.column, col, "data %r col, got %i expected %i" % (d.data, loc.column, col))

class MakeSyntaxTest(TestBase):
    # (string, stopat, stopoffset, expansion
    testdata = (
        ('hello world', '', -1, ['hello world']),
        ('hello $W', '', -1, ['hello ',
                              {'type': 'VariableRef',
                               '.vname': ['W']}
                              ]),
        ('hello: world', ':=', 5, ['hello']),
        ('h $(flavor FOO)', '', -1, ['h ',
                                     {'type': 'FlavorFunction',
                                      '[0]': ['FOO']}
                                     ]),
        ('hello$$world', '', -1, ['hello$world']),
        ('echo $(VAR)', '', -1, ['echo ',
                                 {'type': 'VariableRef',
                                  '.vname': ['VAR']}
                                 ]),
        ('echo $($(VARNAME):.c=.o)', '', -1, ['echo ',
                                              {'type': 'SubstitutionRef',
                                               '.vname': [{'type': 'VariableRef',
                                                           '.vname': ['VARNAME']}
                                                          ],
                                               '.substfrom': ['.c'],
                                               '.substto': ['.o']}
                                              ]),
        ('  $(VAR:VAL) = $(VAL)', ':=', 13, ['  ',
                                             {'type': 'VariableRef',
                                              '.vname': ['VAR:VAL']},
                                             ' ']),
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
                self.assertEqual(type(a), getattr(pymake.data, e['type']),
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
        for s, stopat, stopoffset, expansion in self.testdata:
            d = pymake.parser.Data()
            d.append(s, pymake.parser.Location('testdata', 1, 0))

            a, stoppedat = pymake.parser.parsemakesyntax(d, stopat)
            self.compareRecursive(a, expansion, [])
            self.assertEqual(stoppedat, stopoffset)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
