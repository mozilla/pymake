import pymake.parser
import unittest

class FindCommentTest(unittest.TestCase):
    testdata = (
        ("Hello # Comment", 6),
        ("# Line comment", 0),
        ("No comment", -1),
    )

    def runTest(self):
        for line, expected in self.testdata:
            self.assertEqual(pymake.parser.findcommenthash(line), expected,
                             "findcommenthash: %r" % (line,) )

class IsContinuationTest(unittest.TestCase):
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

class LStripCountTest(unittest.TestCase):
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

class DataTest(unittest.TestCase):
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

if __name__ == '__main__':
    unittest.main()
