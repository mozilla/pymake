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
    continuations. This object is short-lived and should not escape the parser.
    """

    def __init__(self, lineiter, path):
        self.data = ""
        self.lineiter = lineiter
        self.path = path

        # _locs is a list of tuples
        # (dataoffset, location)
        self._locs = []

    def __len__(self):
        return len(self.data)

    def readline(self):
        try:
            lineno, line = self.lineiter.next()
            self.append(line, Location(self.path, lineno, 0))
        except StopIteration:
            pass

    def __getitem__(self, key):
        try:
            return self.data[key]
        except IndexError:
            return None

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

def skipwhitespace(d, offset):
    """
    Return the offset into data after skipping whitespace.
    """
    while True:
        c = d[offset]
        if c is None or not c.isspace():
            break
        offset += 1
    return offset

def setvariable(variables, vname, recursive, value, fromcl=False):
    """
    Parse the remaining data at d[offset] into a variables object.

    @param vname an string holding the variable name
    """
    if len(vname) == 0:
        raise SyntaxError("Empty variable name", loc=d.getloc(offset))

    if fromcl:
        source = data.Variables.SOURCE_OVERRIDE
    else:
        source = data.Variables.SOURCE_MAKEFILE

    if recursive:
        flavor = data.Variables.FLAVOR_RECURSIVE
    else:
        flavor = data.Variables.FLAVOR_SIMPLE
        e = data.Expansion()
        e.append(value.resolve(variables, vname))
        value = e
        
    variables.set(vname, flavor, source, value)

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
            d = Data(None, None)
            d.append(valtext, Location('<command-line>', 1, eqpos + 1))
            value, offset = parsemakesyntax(d, 0, '', iscommand=False)
            assert offset == -1
            setvariable(makefile.variables, vname, a[eqpos-1] != ':', value, True)
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
        d = Data(fdlines, filename)
        if line.startswith('\t') and currule is not None:
            d.append(line[1:], Location(filename, lineno, tabwidth))
            e, stoppedat = parsemakesyntax(d, 0, '', iscommand=True)
            assert stoppedat == -1
            currule.addcommand(e)
        else:
            # To parse Makefile syntax, we first strip leading whitespace and
            # look for initial keywords. If there are no keywords, it's either
            # setting a variable or writing a rule.

            d = Data(fdlines, filename)
            d.append(line, Location(filename, lineno, 0))

            offset = skipwhitespace(d, 0)

            # TODO: look for keywords

            e, stoppedat = parsemakesyntax(d, 0, ':=', iscommand=False)
            if stoppedat == -1:
                v = e.resolve(makefile.variables, None)
                if v.strip() != '':
                    raise SyntaxError("Bad syntax: non-empty line is not a variable assignment or rule.", loc=d.getloc(0))
                continue

            # if we encountered real makefile syntax, the current rule is over
            currule = None

            if d[stoppedat] == '=' or d[stoppedat:stoppedat+2] == ':=':
                isrecursive = d[stoppedat] == '='

                e.lstrip()
                e.rstrip()
                vname = e.resolve(makefile.variables, None)
                value, stoppedat = parsemakesyntax(d, stoppedat + (isrecursive and 1 or 2), '', iscommand=False)
                assert stoppedat == -1
                value.lstrip()
                setvariable(makefile.variables, vname, isrecursive, value)
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
                e, stoppedat = parsemakesyntax(d, stoppedat, ':=|;', iscommand=False)
                if stoppedat == -1 or d[stoppedat] == ';':
                    prereqs = data.splitwords(e.resolve(makefile.variables, None))
                    if ispattern:
                        currule = data.PatternRule(targets, map(data.Pattern, prereqs), doublecolon)
                        makefile.appendimplicitrule(currule)
                    else:
                        currule = data.Rule(prereqs, doublecolon)
                        for t in targets:
                            makefile.gettarget(t.gettarget()).addrule(currule)
                        makefile.foundtarget(targets[0].gettarget())

                    if stoppedat != -1:
                        e, stoppedat = parsemakesyntax(d, stoppedat + 1, '', iscommand=True)
                        assert stoppedat == -1
                        e.lstrip()
                        currule.addcommand(e)
                elif d[stoppedat] == '=' or d[stoppedat:stoppedat+2] == ':=':
                    isrecursive = d[stoppedat] == '='
                    e.lstrip()
                    e.rstrip()
                    vname = e.resolve(makefile.variables, None)
                    value, stoppedat = parsemakesyntax(d, stoppedat + (isrecursive and 1 or 2), '', iscommand=False)
                    assert stoppedat == -1
                    value.lstrip()

                    if ispattern:
                        for target in targets:
                            setvariable(makefile.getpatternvariables(target), vname, isrecursive, value)
                    else:
                        for target in targets:
                            setvariable(makefile.gettarget(target.gettarget()).variables, vname, isrecursive, value)
                elif d[stoppedat] == '|':
                    raise NotImplementedError('order-only prerequisites not implemented')
                else:
                    assert d[stoppedat] == ':'

                    # static pattern rule
                    if ispattern:
                        raise SyntaxError("static pattern rules must have static targets")

                    patstr = e.resolve(makefile.variables, None)
                    patterns = data.splitwords(patstr)
                    if len(patterns) != 1:
                        raise SyntaxError("A static pattern rule may have only one pattern", d.getloc(stoppedat))

                    pattern = data.Pattern(patterns[0])

                    e, stoppedat = parsemakesyntax(d, stoppedat, ';', iscommand=False)
                    prereqs = map(data.Pattern, data.splitwords(e.resolve(makefile.variables, None)))
                    currule = data.PatternRule([pattern], prereqs, doublecolon)
                    for t in targets:
                        makefile.gettarget(t.gettarget()).addrule(currule)

                    makefile.foundtarget(targets[0].gettarget())

                    if stoppedat != -1:
                        e, stoppedat = parsemakesyntax(d, stoppedat + 1, '', iscommand=True)
                        assert stoppedat == -1
                        e.lstrip()
                        currule.addcommand(e)

PARSESTATE_TOPLEVEL = 0    # at the top level
PARSESTATE_FUNCTION = 1    # expanding a function call. data is function

# For the following three, data is a tuple of Expansions: (varname, substfrom, substto)
PARSESTATE_VARNAME = 2     # expanding a variable expansion.
PARSESTATE_SUBSTFROM = 3   # expanding a variable expansion substitution "from" value
PARSESTATE_SUBSTTO = 4     # expanding a variable expansion substitution "to" value

class ParseStackFrame(object):
    def __init__(self, parsestate, expansion, stopon, **kwargs):
        self.parsestate = parsestate
        self.expansion = expansion
        self.stopon = stopon
        for key, value in kwargs.iteritems():
            setattr(self, key, value)

def parsemakesyntax(d, startat, stopon, iscommand):
    """
    Given Data, parse it into a data.Expansion.

    @param stopon (sequence)
        Indicate characters where toplevel parsing should stop.
 
    @return a tuple (expansion, stopoffset). If all the data is consumed, stopoffset will be -1
    """

    # print "parsemakesyntax iscommand=%s" % iscommand

    stack = [
        ParseStackFrame(PARSESTATE_TOPLEVEL, data.Expansion(), stopon)
    ]

    i = startat
    while i < len(d):
        stacktop = stack[-1]
        c = d[i]

        # print "i=%i c=%c parsestate=%i len(d)=%i" % (i, c, stacktop.parsestate, len(d))

        if c == '#' and not iscommand:
            # we need to keep reading lines until there are no more continuations
            while i < len(d):
                if d[i] == '\\':
                    if d[i+1] == '\\':
                        i += 2
                        continue
                    elif d[i+1] == '\n':
                        i += 2
                        assert i == len(d)
                        d.readline()
                elif d[i] == '\n':
                    i += 1
                    assert i == len(d)
                    break
                i += 1
            break
        elif c == '\\':
            # in makefile syntax, backslashes can escape # specially, but nothing else. Fun, huh?
            if d[i+1] is None:
                stacktop.expansion.append('\\')
                i += 1
                break
            elif d[i+1] == '#' and not iscommand:
                stacktop.expansion.append('#')
                i += 2
                continue
            elif d[i+1:i+3] == '\\#':
                # This is an edge case that I discovered. It's undocumented, and
                # totally absolutely weird. See escape-chars.mk VARAWFUL
                stacktop.expansion.append('\\')
                i += 2
                continue
            elif d[i+1] == '\\' and not iscommand:
                stacktop.expansion.append('\\\\')
                i += 2
                continue
            elif d[i+1] == '\n':
                i += 2
                assert i == len(d), "newline isn't last character?"

                d.readline()

                if iscommand:
                    stacktop.expansion.append('\\\n')
                    if d[i] == '\t':
                        i += 1
                else:
                    stacktop.expansion.rstrip()
                    stacktop.expansion.append(' ')
                    i = skipwhitespace(d, i)
                continue
            else:
                stacktop.expansion.append(c)
                i += 1
                continue
        elif c == '\n':
            i += 1
            assert i == len(d), "newline isn't last character?"
            break
        elif c == '$':
            loc = d.getloc(i)
            i += 1
            c = d[i]

            if c == '$':
                stacktop.expansion.append('$')
            elif c == '(':
                # look forward for a function name
                j = i + 1
                while d[j] == '-' or (d[j] >= 'a' and d[j] <= 'z'):
                    j += 1
                fname = d[i + 1:j]
                if d[j] is not None and d[j].isspace() and fname in functions.functionmap:
                    fn = functions.functionmap[fname](loc)
                    stack.append(ParseStackFrame(PARSESTATE_FUNCTION,
                                                 data.Expansion(), ',)',
                                                 function=fn))
                    # skip whitespace before the first argument
                    i = j
                    i = skipwhitespace(d, i + 1)
                    continue
                else:
                    e = data.Expansion()
                    stack.append(ParseStackFrame(PARSESTATE_VARNAME, e, ':)', loc=loc))
            else:
                fe = data.Expansion()
                fe.append(d[i])
                stacktop.expansion.append(functions.VariableRef(loc, fe))
                i += 1
                continue
        elif c in stacktop.stopon:
            if stacktop.parsestate == PARSESTATE_TOPLEVEL:
                break

            if stacktop.parsestate == PARSESTATE_FUNCTION:
                if c == ',':
                    stacktop.function.append(stacktop.expansion)
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
                    stacktop.stopon = '=)'
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
                    stacktop.stopon = ')'
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
        i += 1

    if len(stack) != 1:
        raise SyntaxError("Unterminated function call", d.getloc(len(d) - 1))

    assert stack[0].parsestate == PARSESTATE_TOPLEVEL

    assert i <= len(d), 'overwrote the end: i=%i len(d)=%i' % (i, len(d))

    if i == len(d):
        i = -1
    return stack[0].expansion, i
