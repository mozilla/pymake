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
from pymake import data, functions

tabwidth = 4

log = logging.getLogger('pymake.parser')

class SyntaxError(Exception):
    def __init__(self, message, loc):
        self.message = message
        self.loc = loc

    def __str__(self):
        return "%s: %s" % (self.loc, self.message)

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

    def __str__(self):
        return "%s:%s:%s" % (self.path, self.line, self.column)

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

    def __len__(self):
        return len(self.data)

    def __getitem__(self, key):
        try:
            return self.data[key]
        except IndexError:
            return None

    def append(self, data, loc):
        self._locs.append( (len(self.data), loc) )
        self.data += data

    def stripcomment(self):
        cloc = findcommenthash(self.data)
        if cloc != -1:
            self.data = self.data[:cloc]

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

def skipwhitespace(d, offset):
    """
    Return the offset into data after skipping whitespace.
    """
    while d[offset].isspace():
        offset += 1
    return offset

def parsetoend(d, offset, skipws):
    if skipws:
        offset = skipwhitespace(d, offset)
    value, offset = parsemakesyntax(d, offset, '')
    assert offset == -1
    return value

def setvariable(variables, vname, recursive, value):
    """
    Parse the remaining data at d[offset] into a variables object.

    @param vname an string holding the variable name
    """
    if len(vname) == 0:
        raise SyntaxError("Empty variable name", loc=d.getloc(offset))

    if recursive:
        flavor = data.Variables.FLAVOR_RECURSIVE
    else:
        flavor = data.Variables.FLAVOR_SIMPLE
        e = data.Expansion()
        e.append(value.resolve(variables, vname))
        value = e
        
    variables.set(vname, flavor, data.Variables.SOURCE_MAKEFILE, value)

def parsecommandlineargs(makefile, args):
    """
    Given a set of arguments from a command-line invocation of make,
    parse out the variable definitions and return the rest as targets.
    """

    r = []
    for a in args:
        eqpos = a.find('=')
        if eqpos != -1:
            if a[eqpos-1] == ':':
                vname = a[:eqpos-1]
            else:
                vname = a[:eqpos]
            vname = vname.strip()
            valtext = a[eqpos+1:].lstrip()
            d = Data()
            d.append(valtext, Location('<command-line>', 1, eqpos + 1))
            value, offset = parsemakesyntax(d, 0, '')
            assert offset == -1
            setvariable(makefile.variables, vname, a[eqpos-1] == ':', value)
        else:
            r.append(a)

    return r

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
            isc = iscontinuation(line)
            if not isc:
                line = line[:-1] # strip newline
            d.append(line[1:], Location(filename, lineno, tabwidth))
            while isc:
                lineno, line = fdlines.next()
                startcol = 0
                if line.startswith('\t'):
                    startcol = tabwidth
                    line = line[1:]
                isc = iscontinuation(line)
                if not isc:
                    line = line[:-1] # strip newline
                d.append(line, Location(filename, lineno, startcol))
            currule.addcommand(parsetoend(d, 0, False))
        else:
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
                else:
                    line = line[:-1] # just strip the newline
                d.append(line, Location(filename, lineno, colno))

                if not continues:
                    break

                lineno, line = fdlines.next()

            d.stripcomment()

            e, stoppedat = parsemakesyntax(d, 0, ':=')
            if stoppedat == -1:
                v = e.resolve(makefile.variables, None)
                if v.strip() != '':
                    raise SyntaxError("Bad syntax: non-empty line is not a variable assignment or rule.", loc=d.getloc(0))
                continue

            # if we encountered real makefile syntax, the current rule is over
            currule = None

            if d[stoppedat] == '=' or d[stoppedat:stoppedat+2] == ':=':
                e.rstrip()
                vname = e.resolve(makefile.variables, None)
                value = parsetoend(d, stoppedat + (d[stoppedat] == '=' and 1 or 2), True)
                setvariable(makefile.variables, vname, d[stoppedat] == '=', value)
            else:
                assert d[stoppedat] == ':'

                if d[stoppedat+1] == ':':
                    doublecolon = True
                    stoppedat += 1
                else:
                    doublecolon = False

                # `e` is targets or target patterns, which can end up as
                # * a rule
                # * an implicit rule
                # * a static pattern rule
                # * a target-specific variable definition
                # * a pattern-specific variable definition
                # any of the rules may have order-only prerequisites
                # delimited by |, and a command delimited by ;
                targets = map(data.Pattern, data.splitwords(e.resolve(makefile.variables, None)))
                if len(targets) == 0:
                    raise SyntaxError("No targets in rule", g.getloc(0))

                ispatterns = set((t.ispattern() for t in targets))
                if len(ispatterns) == 2:
                    raise SyntaxError("Mixed implicit and normal rule", d.getloc(0))
                ispattern, = ispatterns

                stoppedat += 1
                e, stoppedat = parsemakesyntax(d, stoppedat, ':=|;')
                if stoppedat == -1:
                    prereqs = data.splitwords(e.resolve(makefile.variables, None))
                    if ispattern:
                        currule = data.PatternRule(targets, map(data.Pattern, prereqs), doublecolon)
                        makefile.appendimplicitrule(currule)
                    else:
                        currule = data.Rule(prereqs, doublecolon)
                        for t in targets:
                            makefile.gettarget(t.gettarget()).addrule(currule)
                        makefile.foundtarget(targets[0].gettarget())
                elif d[stoppedat] == '=' or d[stoppedat:stoppedat+2] == ':=':
                    e.lstrip()
                    e.rstrip()
                    vname = e.resolve(makefile.variables, None)
                    value = parsetoend(d, stoppedat + (d[stoppedat] == '=' and 1 or 2), True)
                    if ispattern:
                        for target in targets:
                            setvariable(makefile.getpatternvariables(target), vname, d[stoppedat] == '=', value)
                    else:
                        for target in targets:
                            setvariable(makefile.gettarget(target.gettarget()).variables, vname, d[stoppedat] == '=', value)
                else:
                    raise NotImplementedError()

PARSESTATE_TOPLEVEL = 0    # at the top level
PARSESTATE_FUNCTION = 1    # expanding a function call. data is function

# For the following three, data is a tuple of Expansions: (varname, substfrom, substto)
PARSESTATE_VARNAME = 2     # expanding a variable expansion.
PARSESTATE_SUBSTFROM = 3   # expanding a variable expansion substitution "from" value
PARSESTATE_SUBSTTO = 4     # expanding a variable expansion substitution "to" value

class ParseStackFrame(object):
    def __init__(self, parsestate, expansion, stopat, **kwargs):
        self.parsestate = parsestate
        self.expansion = expansion
        self.stopat = stopat
        for key, value in kwargs.iteritems():
            setattr(self, key, value)

def parsemakesyntax(d, startat, stopat):
    """
    Given Data, parse it into a data.Expansion.

    @param stopat (sequence)
        Indicate characters where toplevel parsing should stop.
 
    @return a tuple (expansion, stopoffset). If all the data is consumed, stopoffset will be -1
    """

    stack = [
        ParseStackFrame(PARSESTATE_TOPLEVEL, data.Expansion(), stopat)
    ]

    i = startat - 1
    limit = len(d)
    while True:
        i += 1
        if i >= limit:
            break

        stacktop = stack[-1]
        c = d[i]
        if c == '$':
            loc = d.getloc(i)
            i += 1
            c = d[i]

            if c == '$':
                stacktop.expansion.append('$')
            elif c == '(':
                # look forward for a function name
                j = i + 1
                while d[j] >= 'a' and d[j] <= 'z':
                    j += 1
                fname = d[i + 1:j]
                if d[j].isspace() and fname in functions.functionmap:
                    fn = functions.functionmap[fname](loc)
                    stack.append(ParseStackFrame(PARSESTATE_FUNCTION,
                                                 data.Expansion(), ',)',
                                                 function=fn))
                    # skip whitespace before the first argument
                    i = j
                    while d[i+1].isspace():
                        i += 1
                else:
                    e = data.Expansion()
                    stack.append(ParseStackFrame(PARSESTATE_VARNAME, e, ':)', loc=loc))
            else:
                fe = data.Expansion()
                fe.append(d[i])
                stacktop.expansion.append(functions.VariableRef(loc, fe))
                i += 1
        elif c in stacktop.stopat:
            if stacktop.parsestate == PARSESTATE_TOPLEVEL:
                break

            if stacktop.parsestate == PARSESTATE_FUNCTION:
                if c == ',':
                    stacktop.function.append(e)
                    stacktop.expansion = data.Expansion()
                elif c == ')':
                    stacktop.function.append(stacktop.expansion)
                    stacktop.function.setup()
                    stack.pop()
                    stack[-1].expansion.append(stacktop.function)
                else:
                    assert False, "Not reached, PARSESTATE_FUNCTION"
            elif stacktop.parsestate == PARSESTATE_VARNAME:
                if c == ':':
                    stacktop.varname = stacktop.expansion
                    stacktop.parsestate = PARSESTATE_SUBSTFROM
                    stacktop.expansion = data.Expansion()
                    stacktop.stopat = '=)'
                elif c == ')':
                    stack.pop()
                    stack[-1].expansion.append(functions.VariableRef(stacktop.loc, stacktop.expansion))
                else:
                    assert False, "Not reached, PARSESTATE_VARNAME"
            elif stacktop.parsestate == PARSESTATE_SUBSTFROM:
                if c == '=':
                    stacktop.substfrom = stacktop.expansion
                    stacktop.parsestate = PARSESTATE_SUBSTTO
                    stacktop.expansion = data.Expansion()
                    stacktop.stopat = ')'
                elif c == ')':
                    # A substitution of the form $(VARNAME:.ee) is probably a mistake, but make
                    # parses it. Issue a warning. Combine the varname and substfrom expansions to
                    # make the compatible varname. See tests/var-substitutions.mk SIMPLE3SUBSTNAME
                    log.warning("%s: Variable reference looks like substitution without =" % (stacktop.loc, ))
                    stacktop.varname.append(':')
                    stacktop.varname.concat(stacktop.expansion)
                    stack.pop()
                    stack[-1].expansion.append(functions.VariableRef(stacktop.loc, stacktop.varname))
                else:
                    assert False, "Not reached, PARSESTATE_SUBSTFROM"
            elif stacktop.parsestate == PARSESTATE_SUBSTTO:
                assert c == ')', "Not reached, PARSESTATE_SUBSTTO"

                stack.pop()
                stack[-1].expansion.append(functions.SubstitutionRef(stacktop.loc, stacktop.varname,
                                                                     stacktop.substfrom, stacktop.expansion))
            else:
                assert False, "Unexpected parse state %s" % stacktop.parsestate
        else:
            stacktop.expansion.append(c)
    if len(stack) != 1:
        raise SyntaxError("Unterminated function call", d.getloc(len(d) - 1))

    assert stack[0].parsestate == PARSESTATE_TOPLEVEL

    if i >= limit:
        i = -1
    return stack[0].expansion, i
