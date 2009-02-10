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
from cStringIO import StringIO

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
            return True
        except StopIteration:
            return False

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
        if offset is None or offset >= len(self.data):
            offset = len(self.data) - 1

        begin, loc = findlast(lambda (o, l): o <= offset, self._locs)
        return loc + self.data[begin:offset]

    def skipwhitespace(self, offset):
        """
        Return the offset into data after skipping whitespace.
        """
        while offset < len(self.data):
            c = self.data[offset]
            if not c.isspace():
                break
            offset += 1
        return offset

    def findtoken(self, o, tlist, needws):
        """
        Check data at position o for any of the tokens in tlist followed by whitespace
        or end-of-data.

        If a token is found, skip trailing whitespace and return (token, newoffset).
        Otherwise return None, oldoffset
        """
        for t in tlist:
            end = o + len(t)
            if self.data[o:end] == t:
                if not needws:
                    return t, end
                elif end == len(self.data) or self.data[end].isspace():
                    end = self.skipwhitespace(end)
                    return t, end
        return None, o

def iterdata(d, offset):
    """
    A Data iterator yielding (char, offset, location) without any escaping.
    """
    while offset < len(d.data):
        yield d.data[offset], offset, d.getloc(offset)
        offset += 1

def itermakefilechars(d, offset):
    """
    A Data generator yielding (char, offset, location). It will escape comments and newline
    continuations according to makefile syntax rules.
    """

    while offset < len(d.data):
        c = d.data[offset]
        if c == '\n':
            assert offset == len(d.data) - 1
            return

        if c == '#':
            while offset < len(d.data):
                c = d.data[offset]
                if c == '\\' and offset < len(d.data) - 1:
                    offset += 1
                    c = d.data[offset]
                    if c == '\n':
                        assert offset == len(d.data) - 1, 'unexpected newline'
                        d.readline()
                offset += 1
            return
        elif c == '\\' and offset < len(d.data) - 1:
            c2 = d.data[offset + 1]
            if c2 == '#':
                offset += 1
                yield '#', offset, d.getloc(offset)
                offset += 1
            elif d[offset:offset + 3] == '\\\\#':
                # see escape-chars.mk VARAWFUL
                offset += 1
                yield '\\', offset, d.getloc(offset)
                offset += 1
            elif c2 == '\n':
                yield ' ', offset, d.getloc(offset)
                d.readline()
                offset = d.skipwhitespace(offset + 2)
            elif c2 == '\\':
                yield '\\', offset, d.getloc(offset)
                offset += 1
                yield '\\', offset, d.getloc(offset)
                offset += 1
            else:
                yield c, offset, d.getloc(offset)
                offset += 1
        else:
            if c.isspace():
                o = d.skipwhitespace(offset)
                if d.data[o:o+2] == '\\\n':
                    offset = o
                    continue

            yield c, offset, d.getloc(offset)
            offset += 1

def itercommandchars(d, offset):
    """
    A Data generator yielding (char, offset, location). It will process escapes and newlines
    according to command parsing rules.
    """

    while offset < len(d.data):
        c = d.data[offset]
        if c == '\n':
            assert offset == len(d.data) - 1
            return

        yield c, offset, d.getloc(offset)
        offset += 1

        if c == '\\':
            if offset == len(d.data):
                return

            c = d.data[offset]
            yield c, offset, d.getloc(offset)

            offset += 1

            if c == '\n':
                assert offset == len(d.data)
                d.readline()
                if offset < len(d.data) and d.data[offset] == '\t':
                    offset += 1

def iterdefinechars(d, offset):
    """
    A Data generator yielding (char, offset, location). It will process define/endef
    according to define parsing rules.
    """

    def checkfortoken(o):
        """
        Check for a define or endef token on the line starting at o.
        Return an integer for the direction of definecount.
        """
        if o >= len(d.data):
            return 0

        if d.data[o] == '\t':
            return 0

        o = d.skipwhitespace(o)
        token, o = d.findtoken(o, ('define', 'endef'), True)
        if token == 'define':
            return 1

        if token == 'endef':
            return -1
        
        return 0

    startoffset = offset
    definecount = 1 + checkfortoken(offset)
    if definecount == 0:
        return

    while offset < len(d.data):
        c = d.data[offset]

        if c == '\n':
            d.readline()
            definecount += checkfortoken(offset + 1)
            if definecount == 0:
                return

        if c == '\\' and offset < len(d.data) - 1 and d.data[offset+1] == '\n':
            yield ' ', offset, d.getloc(offset)
            d.readline()
            offset = d.skipwhitespace(offset + 2)
            continue

        if c.isspace():
            o = d.skipwhitespace(offset)
            if d.data[o:o+2] == '\\\n':
                offset = o
                continue

        yield c, offset, d.getloc(offset)
        offset += 1


    # Unlike the other iterators, if you fall off this one there is an unterminated
    # define.
    raise SyntaxError("Unterminated define", d.getloc(startoffset))

def ensureend(d, offset, msg, ifunc=itermakefilechars):
    """
    Ensure that only whitespace remains in this data.
    """

    for c, o, l in ifunc(d, offset):
        if not c.isspace():
            raise SyntaxError(msg, d.getloc(offset))

def iterlines(fd):
    """Yield (lineno, line) for each line in fd"""

    lineno = 0
    for line in fd:
        lineno += 1

        if line.endswith('\r\n'):
            line = line[:-2] + '\n'

        yield (lineno, line)

def setvariable(resolvevariables, setvariables, vname, token, d, offset, iterfunc=itermakefilechars, fromcl=False):
    """
    Parse what's left in a data iterator di into a variable.
    """
    assert isinstance(resolvevariables, data.Variables)
    assert isinstance(setvariables, data.Variables)

    # print "setvariable: %r resvariables: %r setvariables: %r" % (vname, resolvevariables, setvariables)

    if len(vname) == 0:
        raise SyntaxError("Empty variable name", loc=d.getloc(offset))

    if fromcl:
        source = data.Variables.SOURCE_OVERRIDE
    else:
        source = data.Variables.SOURCE_MAKEFILE

    if token == '+=':
        val = ''.join((c for c, o, l in iterfunc(d, offset)))
        setvariables.append(vname, source, val, resolvevariables)
        return

    if token == '?=':
        flavor = data.Variables.FLAVOR_RECURSIVE
        val = ''.join((c for c, o, l in iterfunc(d, offset)))
        oldflavor, oldsource, oldval = setvariables.get(vname, expand=False)
        if oldval is not None:
            return
    elif token == '=':
        flavor = data.Variables.FLAVOR_RECURSIVE
        val = ''.join((c for c, o, l in iterfunc(d, offset)))
    else:
        assert token == ':='

        flavor = data.Variables.FLAVOR_SIMPLE
        e, t, o = parsemakesyntax(d, offset, (), itermakefilechars)
        val = e.resolve(resolvevariables, vname)
        
    setvariables.set(vname, flavor, source, val)

def parsecommandlineargs(makefile, args):
    """
    Given a set of arguments from a command-line invocation of make,
    parse out the variable definitions and return the rest as targets.
    """

    r = []
    for i in xrange(0, len(args)):
        a = args[i]

        vname, t, val = a.partition(':=')
        if t == '':
            vname, t, val = a.partition('=')
        if t != '':
            vname = vname.strip()
            d = Data(None, None)
            d.append(val, Location('<command-line>', i, len(vname) + len(t)))

            setvariable(makefile.variables, makefile.variables,
                        vname, t, d, 0, fromcl=True,
                        iterfunc=iterdata)
        else:
            r.append(a)

    return r

def ifeq(d, offset, makefile):
    # the variety of formats for this directive is rather maddening
    token, offset = d.findtoken(offset, ('(', "'", '"'), False)
    if token is None:
        raise SyntaxError("No arguments after conditional", d.getloc(offset))

    if token == '(':
        arg1, t, offset = parsemakesyntax(d, offset, (',',), itermakefilechars)
        if t is None:
            raise SyntaxError("Expected two arguments in conditional", d.getloc(offset))

        offset = d.skipwhitespace(offset)
        arg2, t, offset = parsemakesyntax(d, offset, (')',), itermakefilechars)
        if t is None:
            raise SyntaxError("Unexpected text in conditional", d.getloc(offset))

        ensureend(d, offset, "Unexpected text after conditional")
    else:
        arg1, t, offset = parsemakesyntax(d, offset, (token,), itermakefilechars)
        if t is None:
            raise SyntaxError("Unexpected text in conditional", d.getloc(offset))

        offset = d.skipwhitespace(offset)
        if offset == len(d):
            raise SyntaxError("Expected two arguments in conditional", d.getloc(offset))

        token = d[offset]
        if token not in '\'"':
            raise SyntaxError("Unexpected text in conditional", d.getloc(offset))

        arg2, t, offset = parsemakesyntax(d, offset + 1, (token,), itermakefilechars)

        ensureend(d, offset, "Unexpected text after conditional")

    val1 = arg1.resolve(makefile.variables, None)
    val2 = arg2.resolve(makefile.variables, None)
    return val1 == val2

def ifneq(d, offset, makefile):
    return not ifeq(d, offset, makefile)

def ifdef(d, offset, makefile):
    e, t, offset = parsemakesyntax(d, offset, (), itermakefilechars)
    e.rstrip()

    vname = e.resolve(makefile.variables, None)

    flavor, source, value = makefile.variables.get(vname, expand=False)

    if value is None:
        return False

    # We aren't expanding the variable... we're just seeing if it was set to a non-empty
    # expansion.
    return len(value) > 0

def ifndef(d, offset, makefile):
    return not ifdef(d, offset, makefile)

conditionkeywords = {
    'ifeq': ifeq,
    'ifneq': ifneq,
    'ifdef': ifdef,
    'ifndef': ifndef
    }

class Condition(object):
    """
    Represent aa makefile conditional.
    1) is the condition active right now?
    2) was the condition ever met?
    """
    def __init__(self, active, loc):
        self.active = active
        self.everactive = active

    def makeactive(self, active):
        if self.everactive:
            self.active = False
            return

        self.active = active
        if active:
            self.everactive = True

directives = [k for k in conditionkeywords.iterkeys()] + \
    ['else', 'endif', 'define', 'endef', 'override', 'include', '-include', 'vpath']

varsettokens = (':=', '+=', '?=', '=')

def parsestream(fd, filename, makefile):
    """
    Parse a stream of makefile into a makefile data structure.

    @param fd A file-like object containing the makefile data.
    """

    currule = None
    condstack = []

    fdlines = iterlines(fd)

    while True:
        d = Data(fdlines, filename)
        if not d.readline():
            break

        if len(d.data) > 0 and d.data[0] == '\t' and currule is not None:
            if any((not c.active for c in condstack)):
                log.info('%s: skipping line because of active conditions' % (d.getloc(0),))
                continue

            e, t, o = parsemakesyntax(d, 1, (), itercommandchars)
            assert t == None
            currule.addcommand(e)
        else:
            # To parse Makefile syntax, we first strip leading whitespace and
            # look for initial keywords. If there are no keywords, it's either
            # setting a variable or writing a rule.

            offset = d.skipwhitespace(0)

            kword, offset = d.findtoken(offset, directives, True)
            if kword == 'endif':
                ensureend(d, offset, "Unexpected data after 'endif' directive")
                if not len(condstack):
                    raise SyntaxError("unmatched 'endif' directive",
                                      d.getloc(offset))

                condstack.pop()
                continue
            
            if kword == 'else':
                if not len(condstack):
                    raise SyntaxError("unmatched 'else' directive",
                                      d.getloc(offset))

                kword, offset = d.findtoken(offset, conditionkeywords, True)
                if kword is None:
                    ensureend(d, offset, "Unexpected data after 'else' directive.")
                    condstack[-1].makeactive(True)
                else:
                    if kword not in conditionkeywords:
                        raise SyntaxError("Unexpected condition after 'else' directive.",
                                          d.getloc(offset))
                        
                    m = conditionkeywords[kword](d, offset, makefile)
                    condstack[-1].makeactive(m)
                continue

            if kword == 'endef':
                raise SyntaxError("Unmatched endef", d.getloc(offset))

            if kword == 'override':
                raise NotImplementedError('no overrides yet')

            if kword == 'define':
                e, t, i = parsemakesyntax(d, offset, (), itermakefilechars)

                d = Data(fdlines, filename)
                d.readline()

                setvariable(makefile.variables, makefile.variables,
                            e.resolve(makefile.variables, None),
                            '=', d, 0, iterdefinechars)

                continue

            if kword in ('include', '-include'):
                incfile, t, offset = parsemakesyntax(d, offset, (), itermakefilechars)
                files = data.splitwords(incfile.resolve(makefile.variables, None))
                for f in files:
                    makefile.include(f, kword == 'include')
                continue

            if kword in conditionkeywords:
                m = conditionkeywords[kword](d, offset, makefile)
                condstack.append(Condition(m, d.getloc(offset)))
                continue

            assert kword is None

            if any((not c.active for c in condstack)):
                log.info('%s: skipping line because of active conditions' % (d.getloc(0),))
                continue

            e, token, offset = parsemakesyntax(d, offset, varsettokens + ('::', ':'), itermakefilechars)
            if token is None:
                v = e.resolve(makefile.variables, None)
                if v.strip() != '':
                    raise SyntaxError("Bad syntax: non-empty line is not a variable assignment or rule.", loc=d.getloc(0))
                continue

            # if we encountered real makefile syntax, the current rule is over
            currule = None

            if token in varsettokens:
                e.lstrip()
                e.rstrip()
                vname = e.resolve(makefile.variables, None)

                offset = d.skipwhitespace(offset)

                setvariable(makefile.variables, makefile.variables,
                            vname, token, d, offset)
            else:
                doublecolon = token == '::'

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
                    raise SyntaxError("No targets in rule", g.getloc(offset))

                ispatterns = set((t.ispattern() for t in targets))
                if len(ispatterns) == 2:
                    raise SyntaxError("Mixed implicit and normal rule", d.getloc(offset))
                ispattern, = ispatterns

                e, token, offset = parsemakesyntax(d, offset,
                                                   varsettokens + (':', '|', ';'),
                                                   itermakefilechars)
                if token in (None, ';'):
                    prereqs = data.splitwords(e.resolve(makefile.variables, None))
                    if ispattern:
                        currule = data.PatternRule(targets, map(data.Pattern, prereqs), doublecolon, loc=d.getloc(0))
                        makefile.appendimplicitrule(currule)
                    else:
                        currule = data.Rule(prereqs, doublecolon, loc=d.getloc(0))
                        for t in targets:
                            makefile.gettarget(t.gettarget()).addrule(currule)
                        makefile.foundtarget(targets[0].gettarget())

                    if token == ';':
                        offset = d.skipwhitespace(offset)
                        e, t, offset = parsemakesyntax(d, offset, (), itercommandchars)
                        currule.addcommand(e)
                elif token in varsettokens:
                    e.lstrip()
                    e.rstrip()
                    vname = e.resolve(makefile.variables, None)

                    offset = d.skipwhitespace(offset)
                    if ispattern:
                        for target in targets:
                            setvariable(makefile.variables,
                                        makefile.getpatternvariables(target), vname,
                                        token, d, offset)
                    else:
                        for target in targets:
                            setvariable(makefile.variables,
                                        makefile.gettarget(target.gettarget()).variables,
                                        vname, token, d, offset)
                elif token == '|':
                    raise NotImplementedError('order-only prerequisites not implemented')
                else:
                    assert token == ':'

                    # static pattern rule
                    if ispattern:
                        raise SyntaxError("static pattern rules must have static targets")

                    patstr = e.resolve(makefile.variables, None)
                    patterns = data.splitwords(patstr)
                    if len(patterns) != 1:
                        raise SyntaxError("A static pattern rule may have only one pattern", d.getloc(offset))

                    pattern = data.Pattern(patterns[0])

                    e, token, offset = parsemakesyntax(d, offset, (';',), itermakefilechars)
                    prereqs = map(data.Pattern, data.splitwords(e.resolve(makefile.variables, None)))
                    currule = data.PatternRule([pattern], prereqs, doublecolon, loc=d.getloc(0))
                    for t in targets:
                        makefile.gettarget(t.gettarget()).addrule(currule)

                    makefile.foundtarget(targets[0].gettarget())

                    if token == ';':
                        offset = d.skipwhitespace(offset)
                        e, token, offset = parsemakesyntax(d, offset, (), itercommandchars)
                        currule.addcommand(e)

    if len(condstack):
        raise SyntaxError("Condition never terminated with endif", condstack[-1].loc)

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

functiontokens = [k for k in functions.functionmap.iterkeys()]

def parsemakesyntax(d, startat, stopon, iterfunc):
    """
    Given Data, parse it into a data.Expansion.

    @param stopon (sequence)
        Indicate characters where toplevel parsing should stop.

    @param iterfunc (generator function)
        A function which is used to iterate over d, yielding (char, offset, loc)
        @see iterdata
        @see itermakefilechars
        @see itercommandchars
 
    @return a tuple (expansion, token, offset). If all the data is consumed,
    token and offset will be None
    """

    # print "parsemakesyntax(%r)" % d.data

    assert callable(iterfunc)

    stack = [
        ParseStackFrame(PARSESTATE_TOPLEVEL, data.Expansion(), stopon)
    ]

    di = iterfunc(d, startat)
    offset = startat

    while True: # this is not a for loop because `di` changes during the function
        stacktop = stack[-1]
        try:
            c, offset, loc = di.next()
        except StopIteration:
            break

        # print "  %i: stacklen=%i parsestate=%s looking for %r" % (offset, len(stack),
        #                                                           stacktop.parsestate, stacktop.stopon),

        token, offset = d.findtoken(offset, stacktop.stopon, False)
        if token is not None:
            c = 'dangerwillrobinson!'
            di = iterfunc(d, offset)

            if stacktop.parsestate == PARSESTATE_TOPLEVEL:
                assert len(stack) == 1
                return stacktop.expansion, token, offset

            if stacktop.parsestate == PARSESTATE_FUNCTION:
                if token == ',':
                    stacktop.function.append(stacktop.expansion)
                    stacktop.expansion = data.Expansion()
                elif token == ')':
                    stacktop.function.append(stacktop.expansion)
                    stacktop.function.setup()
                    stack.pop()
                    stack[-1].expansion.append(stacktop.function)
                else:
                    assert False, "Not reached, PARSESTATE_FUNCTION"
            elif stacktop.parsestate == PARSESTATE_VARNAME:
                if token == ':':
                    stacktop.varname = stacktop.expansion
                    stacktop.parsestate = PARSESTATE_SUBSTFROM
                    stacktop.expansion = data.Expansion()
                    stacktop.stopon = ('=', ')')
                elif token == ')':
                    stack.pop()
                    stack[-1].expansion.append(functions.VariableRef(stacktop.loc, stacktop.expansion))
                else:
                    assert False, "Not reached, PARSESTATE_VARNAME"
            elif stacktop.parsestate == PARSESTATE_SUBSTFROM:
                if token == '=':
                    stacktop.substfrom = stacktop.expansion
                    stacktop.parsestate = PARSESTATE_SUBSTTO
                    stacktop.expansion = data.Expansion()
                    stacktop.stopon = (')',)
                elif token == ')':
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
                assert token == ')', "Not reached, PARSESTATE_SUBSTTO"

                stack.pop()
                stack[-1].expansion.append(functions.SubstitutionRef(stacktop.loc, stacktop.varname,
                                                                     stacktop.substfrom, stacktop.expansion))
            else:
                assert False, "Unexpected parse state %s" % stacktop.parsestate

            continue
        elif c == '$':
            try:
                c, offset, loc = di.next()
            except StopIteration:
                # an un-terminated $ expands to nothing
                break

            if c == '$':
                stacktop.expansion.append('$')
                continue

            if c == '(':
                # look forward for a function name
                fname, offset = d.findtoken(offset + 1, functiontokens, True)
                if fname is not None:
                    fn = functions.functionmap[fname](loc)
                    stack.append(ParseStackFrame(PARSESTATE_FUNCTION,
                                                 data.Expansion(), ',)',
                                                 function=fn))
                    di = iterfunc(d, offset)
                    continue

                e = data.Expansion()
                stack.append(ParseStackFrame(PARSESTATE_VARNAME, e, (':', ')'), loc=loc))
                continue

            fe = data.Expansion()
            fe.append(c)
            stacktop.expansion.append(functions.VariableRef(loc, fe))
            continue

        else:
            stacktop.expansion.append(c)

    if len(stack) != 1:
        raise SyntaxError("Unterminated function call", d.getloc(len(d) - 1))

    assert stack[0].parsestate == PARSESTATE_TOPLEVEL

    return stack[0].expansion, None, None
