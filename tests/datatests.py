import pymake.data
import unittest
import re

class SplitWordsTest(unittest.TestCase):
    testdata = (
        (' test test.c test.o ', ['test', 'test.c', 'test.o']),
        ('\ttest\t  test.c \ntest.o', ['test', 'test.c', 'test.o']),
    )

    def runTest(self):
        for s, e in self.testdata:
            w = pymake.data.splitwords(s)
            self.assertEqual(w, e, 'splitwords(%r)' % (s,))

class GetPatSubstTest(unittest.TestCase):
    testdata = (
        ('%.c', '%.o', ' test test.c test.o ', 'test test.o test.o'),
        ('%', '%.o', ' test.c test.o ', 'test.c.o test.o.o'),
        ('foo', 'bar', 'test foo bar', 'test bar bar'),
        ('foo', '%bar', 'test foo bar', 'test %bar bar'),
    )

    def runTest(self):
        for s, r, d, e in self.testdata:
            words = pymake.data.splitwords(d)
            search, replace = pymake.data.getpatsubst(s, r)
            sre = re.compile(search)
            a = ' '.join((sre.sub(replace, word)
                          for word in words))
            self.assertEqual(a, e, 'getpatsubst(%r) got %r (search=%r replace=%r)' % (d, a, search, replace))

if __name__ == '__main__':
    unittest.main()
