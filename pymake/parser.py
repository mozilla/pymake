"""
Module for parsing Makefile syntax.

Makefiles use a line-based parsing system. Continuations and substitutions are handled differently based on the
type of line being parsed:

Lines with makefile syntax condense continuations to a single space, no matter the actual trailing whitespace
of the first line or the leading whitespace of the continuation. In other situations, trailing whitespace is
relevant.

Lines with command syntax do not condense continuations: the backslash and newline are part of the command.
(GNU Make is buggy in this regard, at least on mac).

Lines with an initial tab are commands if they can be (there is a rule or a command immediately preceding).
Otherwise, they are parsed as makefile syntax.

After splitting data into parseable chunks, we use a recursive-descent parser to
nest parenthesized syntax.
"""

import logging

tabwidth = 4

log = logging.getLogger('pymake.parser')

class Location(object):
    """
    A location within a makefile.

    For the moment, locations are just path/line/column, but in the future
    they may reference parent locations for more accurate "included from"
    or "evaled at" error reporting.
    """
    __slots__ = ('path', 'line', 'column')

    def __init__(self, path, line, column):
        self.path = path
        self.line = line
        self.column = column

    def __add__(self, data):
        """
        Returns a new location on the same line offset by
        the specified string.
        """
        newcol = reduce(charlocation, data, self.column)
        if newcol == self.column:
            return self
        return Location(self.path, self.line, newcol)

def findcommenthash(line):
    """
    Search a line for the location of a comment hash. Returns -1 if there is
    no comment.
    """
    i = 0
    limit = len(line)
    while i < limit:
        if line[i] == '#':
            return i
        if line[i] == '\\':
            i += 1
        i += 1
    return -1

def iscontinuation(line):
    """
    A line continues only when the last *unmatched* backslash is before the
    newline... this isn't documented, though.
    """
    i = 0
    limit = len(line)
    while i < limit:
        if line[i] == '\\':
            i += 1
            if i != limit and line[i] == '\n':
                return True
        i += 1

    return False

def lstripcount(line):
    """
    Do an lstrip, but keep track how many columns were stripped for location-
    tracking purposes. Returns (stripped, column)
    """
    r = line.lstrip()
    return (r, reduce(charlocation, line[:len(line) - len(r)], 0))

def findlast(func, iterable):
    f = None
    for i in iterable:
        if func(i):
            f = i
        else:
            return f

    return f

def charlocation(start, char):
    """
    Return the column position after processing a perhaps-tab character.
    This function is meant to be used with reduce().
    """
    if char != '\t':
        return start + 1

    return start + tabwidth - start % tabwidth

class Data(object):
    """
    A single virtual "line", which can be multiple source lines joined with
    continuations.
    """

    __slots__ = ('data', '_locs')

    def __init__(self):
        self.data = ""

        # _locs is a list of tuples
        # (dataoffset, location)
        self._locs = []

    def append(self, data, loc):
        self._locs.append( (len(self.data), loc) )
        self.data += data

    def getloc(self, offset):
        """
        Get the location of an offset within data.
        """
        if offset >= len(self.data):
            raise IndexError("Invalid offset", offset)

        begin, loc = findlast(lambda (o, l): o <= offset, self._locs)
        return loc + self.data[begin:offset]

def _iterlines(fd):
    """Yield (lineno, line) for each line in fd"""

    lineno = 0
    for line in fd:
        lineno += 1

        if line.endswith('\r\n'):
            line = line[:-2] + '\n'
        yield (lineno, line)

def parsestream(fd, filename, makefile):
    """
    Parse a stream of makefile into a makefile data structure.

    @param fd A file-like object containing the makefile data.
    """

    currule = None

    fdlines = _iterlines(fd)

    for lineno, line in fdlines:
        if line.startswith('\t') and currule is not None:
            d = Data()
            d.append(line[1:], Location(filename, lineno, tabwidth))
            while iscontinuation(line):
                lineno, line = fdlines.next()
                startcol = 0
                if line.startwith('\t'):
                    startcol = tabwith
                    line = line[1:]
                d.append(line, Location(filename, lineno, startcol))
            currule.addcommand(parsecommand(d))
        else:
            currule = None

            # To parse Makefile syntax, we first strip leading whitespace and
            # join continued lines, then look for initial keywords. If there
            # are no keywords, it's either setting a variable or writing a
            # rule.

            d = Data()

            while True:
                line, colno = lstripcount(line)
                continues = iscontinuation(line)
                if continues:
                    line = line[:-2].rstrip() + ' '
                d.append(line, Location(filename, lineno, 0))

                if not continues:
                    break

                lineno, line = fdlines.next()

            

            parsemakedata(d)

def _parsemakesyntax(d, stopshort):
    """
    Given Data, parse it into a data.Expansion.

    @param stopshort (boolean)
        if False, all the remaining data is parsed, and the function returns
        the Expansion.
 
        if True, the data is parsed up to a makefile separator (equals sign
        or colon), and the function returns (expansion, offset)
    """
