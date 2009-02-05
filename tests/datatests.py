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
        ('%', 'perc_%', 'path', 'perc_path'),
        ('\\%', 'sub%', 'p %', 'p sub%'),
        ('%.c', '\\%%.o', 'foo.c bar.o baz.cpp', '%foo.o bar.o baz.cpp'),
    )

    def runTest(self):
        for s, r, d, e in self.testdata:
            words = pymake.data.splitwords(d)
            p = pymake.data.Pattern(s)
            a = ' '.join((p.subst(r, word, False)
                          for word in words))
            self.assertEqual(a, e, 'Pattern(%r).subst(%r, %r)' % (s, r, d))

if __name__ == '__main__':
    unittest.main()
