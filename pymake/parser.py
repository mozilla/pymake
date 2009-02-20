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

import logging, re
import data, functions, util
from pymake.globrelative import hasglob, glob
from cStringIO import StringIO

tabwidth = 4

log = logging.getLogger('pymake.parser')

class SyntaxError(util.MakeError):
    pass

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

        if offset == -1:
            offset = 0

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

    def findtoken(self, o, tlist, skipws):
        """
        Check data at position o for any of the tokens in tlist followed by whitespace
        or end-of-data.

        If a token is found, skip trailing whitespace and return (token, newoffset).
        Otherwise return None, oldoffset
        """
        assert isinstance(tlist, TokenList)

        if skipws:
            m = tlist.wslist.match(self.data, pos=o)
            if m is not None:
                return m.group(1), m.end(0)
        else:
            m = tlist.simplere.match(self.data, pos=o)
            if m is not None:
                return m.group(0), m.end(0)

        return None, o

makefiletokensescaped = [r'\\\\#', r'\\#', '\\\\\n', '\\\\\\s+\\\\\n', r'\\.', '#', '\n']
continuationtokensescaped = ['\\\\\n', r'\\.', '\n']

class TokenList(object):
    """
    A list of tokens to search. Because these lists are static, we can perform
    optimizations (such as escaping and compiling regexes) on construction.
    """
    def __init__(self, tlist):
        self.emptylist = len(tlist) == 0
        escapedlist = [re.escape(t) for t in tlist]
        self.simplere = re.compile('|'.join(escapedlist))
        self.makefilere = re.compile('|'.join(escapedlist + makefiletokensescaped))
        self.continuationre = re.compile('|'.join(escapedlist + continuationtokensescaped))

        self.wslist = re.compile('(' + '|'.join(escapedlist) + ')' + r'(\s+|$)')

    imap = {}

    @staticmethod
    def get(s):
        if s in TokenList.imap:
            return TokenList.imap[s]

        i = TokenList(s)
        TokenList.imap[s] = i
        return i

emptytokenlist = TokenList.get('')

# The following four iterators handle line continuations and comments in
# different ways, but share a similar behavior:
#
# Called with (data, startoffset, tokenlist)
#
# yield 4-tuples (flatstr, token, tokenoffset, afteroffset)
# flatstr is data, guaranteed to have no tokens (may be '')
# token, tokenoffset, afteroffset *may be None*. That means there is more text
# coming.

def iterdata(d, offset, tokenlist):
    if tokenlist.emptylist:
        yield d.data, None, None, None
        return

    s = tokenlist.simplere

    while offset < len(d.data):
        m = s.search(d.data, pos=offset)
        if m is None:
            yield d.data[offset:], None, None, None
            return

        yield d.data[offset:m.start(0)], m.group(0), m.start(0), m.end(0)
        offset = m.end(0)

def itermakefilechars(d, offset, tokenlist):
    s = tokenlist.makefilere

    while offset < len(d.data):
        m = s.search(d.data, pos=offset)
        if m is None:
            yield d.data[offset:], None, None, None
            return

        token = m.group(0)
        start = m.start(0)
        end = m.end(0)

        if token == '\n':
            assert end == len(d.data)
            yield d.data[offset:start], None, None, None
            return

        if token == '#':
            yield d.data[offset:start], None, None, None
            for s in itermakefilechars(d, end, emptytokenlist): pass
            return

        if token == '\\\\#':
            # see escape-chars.mk VARAWFUL
            yield d.data[offset:start + 1], None, None, None
            for s in itermakefilechars(d, end, emptytokenlist): pass
            return

        if token == '\\\n':
            yield d.data[offset:start].rstrip() + ' ', None, None, None
            d.readline()
            offset = d.skipwhitespace(end)
            continue

        if token.startswith('\\') and token.endswith('\n'):
            assert end == len(d.data)
            yield d.data[offset:start] + '\\ ', None, None, None
            d.readline()
            offset = d.skipwhitespace(end)
            continue

        if token == '\\#':
            yield d.data[offset:start] + '#', None, None, None
        elif token.startswith('\\'):
            yield d.data[offset:end], None, None, None
        else:
            yield d.data[offset:start], token, start, end

        offset = end

def itercommandchars(d, offset, tokenlist):
    s = tokenlist.continuationre

    while offset < len(d.data):
        m = s.search(d.data, pos=offset)
        if m is None:
            yield d.data[offset:], None, None, None
            return

        token = m.group(0)
        start = m.start(0)
        end = m.end(0)

        if token == '\n':
            assert end == len(d.data)
            yield d.data[offset:start], None, None, None
            return

        if token == '\\\n':
            yield d.data[offset:end], None, None, None
            d.readline()
            offset = end
            if offset < len(d.data) and d.data[offset] == '\t':
                offset += 1
            continue
        
        if token.startswith('\\'):
            yield d.data[offset:end], None, None, None
        else:
            yield d.data[offset:start], token, start, end

        offset = end

definestokenlist = TokenList.get(('define', 'endef'))

def iterdefinechars(d, offset, tokenlist):
    """
    A Data generator yielding (char, offset). It will process define/endef
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
        token, o = d.findtoken(o, definestokenlist, True)
        if token == 'define':
            return 1

        if token == 'endef':
            return -1
        
        return 0

    startoffset = offset
    definecount = 1 + checkfortoken(offset)
    if definecount == 0:
        return

    s = tokenlist.continuationre

    while offset < len(d.data):
        m = s.search(d.data, pos=offset)
        if m is None:
            yield d.data[offset:], None, None, None
            break

        token = m.group(0)
        start = m.start(0)
        end = m.end(0)

        if token == '\\\n':
            yield d.data[offset:start].rstrip() + ' ', None, None, None
            d.readline()
            offset = d.skipwhitespace(end)
            continue

        if token == '\n':
            assert end == len(d.data)
            d.readline()
            definecount += checkfortoken(end)
            if definecount == 0:
                yield d.data[offset:start], None, None, None
                return

            yield d.data[offset:end], None, None, None
        elif token.startswith('\\'):
            yield d.data[offset:end], None, None, None
        else:
            yield d.data[offset:start], token, start, end

        offset = end

    # Unlike the other iterators, if you fall off this one there is an unterminated
    # define.
    raise SyntaxError("Unterminated define", d.getloc(startoffset))

def ensureend(d, offset, msg, ifunc=itermakefilechars):
    """
    Ensure that only whitespace remains in this data.
    """

    for c, t, o, oo in ifunc(d, offset, emptytokenlist):
        if c != '' and not c.isspace():
            raise SyntaxError(msg, d.getloc(o))

def iterlines(fd):
    """Yield (lineno, line) for each line in fd"""

    lineno = 0
    for line in fd:
        lineno += 1

        if line.endswith('\r\n'):
            line = line[:-2] + '\n'

        yield (lineno, line)

def setvariable(resolvevariables, setvariables, makefile, vname, token, d, offset,
                iterfunc=itermakefilechars, source=None,
                skipwhitespace=True):
    """
    Parse what's left in a data iterator di into a variable.
    """
    assert isinstance(resolvevariables, data.Variables)
    assert isinstance(setvariables, data.Variables)

    if source is None:
        source = data.Variables.SOURCE_MAKEFILE

    # print "setvariable: %r resvariables: %r setvariables: %r" % (vname, resolvevariables, setvariables)

    if len(vname) == 0:
        raise SyntaxError("Empty variable name", loc=d.getloc(offset))

    if token == '+=':
        val = ''.join((c for c, t, o, oo in iterfunc(d, offset, emptytokenlist)))
        if skipwhitespace:
            val = val.lstrip()
        setvariables.append(vname, source, val, resolvevariables, makefile)
        return

    if token == '?=':
        flavor = data.Variables.FLAVOR_RECURSIVE
        val = ''.join((c for c, t, o, oo in iterfunc(d, offset, emptytokenlist)))
        if skipwhitespace:
            val = val.lstrip()
        oldflavor, oldsource, oldval = setvariables.get(vname, expand=False)
        if oldval is not None:
            return
    elif token == '=':
        flavor = data.Variables.FLAVOR_RECURSIVE
        val = ''.join((c for c, t, o, oo in iterfunc(d, offset, emptytokenlist)))
        if skipwhitespace:
            val = val.lstrip()
    else:
        assert token == ':='

        flavor = data.Variables.FLAVOR_SIMPLE
        e, t, o = parsemakesyntax(d, offset, (), itermakefilechars)
        if skipwhitespace:
            e.lstrip()
        val = e.resolve(makefile, resolvevariables)
        
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
            makefile.overrides.append(a)

            vname = vname.strip()
            d = Data(None, None)
            d.append(val, Location('<command-line>', i, len(vname) + len(t)))

            setvariable(makefile.variables, makefile.variables, makefile,
                        vname, t, d, 0, source=data.Variables.SOURCE_COMMANDLINE,
                        iterfunc=iterdata)
        else:
            r.append(a)

    return r

eqargstokenlist = TokenList.get(('(', "'", '"'))

def ifeq(d, offset, makefile):
    # the variety of formats for this directive is rather maddening
    token, offset = d.findtoken(offset, eqargstokenlist, False)
    if token is None:
        raise SyntaxError("No arguments after conditional", d.getloc(offset))

    if token == '(':
        arg1, t, offset = parsemakesyntax(d, offset, (',',), itermakefilechars)
        if t is None:
            raise SyntaxError("Expected two arguments in conditional", d.getloc(offset))

        arg1.rstrip()

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

    val1 = arg1.resolve(makefile, makefile.variables)
    val2 = arg2.resolve(makefile, makefile.variables)

    return val1 == val2

def ifneq(d, offset, makefile):
    return not ifeq(d, offset, makefile)

def ifdef(d, offset, makefile):
    e, t, offset = parsemakesyntax(d, offset, (), itermakefilechars)
    e.rstrip()

    vname = e.resolve(makefile, makefile.variables)

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

def expandwildcards(makefile, tlist):
    for t in tlist:
        if not hasglob(t):
            yield t
        else:
            l = glob(makefile.workdir, t)
            for r in l:
                yield r

conditiontokens = tuple(conditionkeywords.iterkeys())
directivestokenlist = TokenList.get(conditiontokens + \
    ('else', 'endif', 'define', 'endef', 'override', 'include', '-include', 'vpath', 'export', 'unexport'))
conditionkeywordstokenlist = TokenList.get(conditiontokens)

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
                log.debug('%s: skipping line because of active conditions' % (d.getloc(0),))
                continue

            e, t, o = parsemakesyntax(d, 1, (), itercommandchars)
            assert t == None
            currule.addcommand(e)
        else:
            # To parse Makefile syntax, we first strip leading whitespace and
            # look for initial keywords. If there are no keywords, it's either
            # setting a variable or writing a rule.

            offset = d.skipwhitespace(0)

            kword, offset = d.findtoken(offset, directivestokenlist, True)
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

                kword, offset = d.findtoken(offset, conditionkeywordstokenlist, True)
                if kword is None:
                    ensureend(d, offset, "Unexpected data after 'else' directive.")
                    condstack[-1].makeactive(True)
                else:
                    if kword not in conditionkeywords:
                        raise SyntaxError("Unexpected condition after 'else' directive.",
                                          d.getloc(offset))

                    if any ((not c.active for c in condstack[:-1])):
                        pass
                    else:
                        m = conditionkeywords[kword](d, offset, makefile)
                        condstack[-1].makeactive(m)
                continue

            if kword in conditionkeywords:
                if any((not c.active for c in condstack)):
                    # If any conditions are currently false, we don't evaluate anything: just stick a dummy
                    # condition on the stack
                    condstack.append(Condition(True, d.getloc(offset)))
                else:
                    m = conditionkeywords[kword](d, offset, makefile)
                    condstack.append(Condition(m, d.getloc(offset)))
                continue

            if any((not c.active for c in condstack)):
                log.debug('%s: skipping line because of active conditions' % (d.getloc(0),))
                for c in itermakefilechars(d, offset, emptytokenlist):
                    pass
                continue

            if kword == 'endef':
                raise SyntaxError("Unmatched endef", d.getloc(offset))

            if kword == 'define':
                e, t, i = parsemakesyntax(d, offset, (), itermakefilechars)

                d = Data(fdlines, filename)
                d.readline()

                setvariable(makefile.variables, makefile.variables, makefile,
                            e.resolve(makefile, makefile.variables),
                            '=', d, 0, iterdefinechars,
                            skipwhitespace=False)

                continue

            if kword in ('include', '-include'):
                incfile, t, offset = parsemakesyntax(d, offset, (), itermakefilechars)
                files = data.splitwords(incfile.resolve(makefile, makefile.variables))
                for f in files:
                    makefile.include(f.replace('\\','/'),
                                     kword == 'include', loc=d.getloc(offset))
                continue

            if kword == 'vpath':
                e, t, offset = parsemakesyntax(d, offset, (' ', '\t'), itermakefilechars)
                patstr = e.resolve(makefile, makefile.variables)
                pattern = data.Pattern(patstr)
                if t is None:
                    makefile.clearallvpaths()
                else:
                    e, t, offset = parsemakesyntax(d, offset, (), itermakefilechars)
                    dirs = e.resolve(makefile, makefile.variables)
                    dirlist = []
                    for direl in data.splitwords(dirs):
                        dirlist.extend((dir
                                        for dir in direl.split(':')
                                        if dir != ''))

                    if len(dirlist) == 0:
                        makefile.clearvpath(pattern)
                    else:
                        makefile.addvpath(pattern, dirlist)
                continue

            if kword == 'override':
                e, token, offset = parsemakesyntax(d, offset, varsettokens, itermakefilechars)
                e.lstrip()
                e.rstrip()

                if token is None:
                    raise SyntaxError("Malformed override directive, need =", d.getloc(offset))

                vname = e.resolve(makefile, makefile.variables)
                setvariable(makefile.variables, makefile.variables, makefile,
                            vname, token, d, offset,
                            source=data.Variables.SOURCE_OVERRIDE)
                continue

            if kword == 'export':
                e, token, offset = parsemakesyntax(d, offset, varsettokens, itermakefilechars)
                e.lstrip()
                e.rstrip()
                vars = e.resolve(makefile, makefile.variables)
                if token is None:
                    vlist = data.splitwords(vars)
                    if len(vlist) == 0:
                        raise SyntaxError("Exporting all variables is not supported", d.getloc(offset))
                else:
                    vlist = [vars]
                    setvariable(makefile.variables, makefile.variables, makefile,
                                vars, token, d, offset)

                for v in vlist:
                    makefile.exportedvars.add(v)

                continue

            if kword == 'unexport':
                raise SyntaxError("unexporting variables is not supported", d.getloc(offset))

            assert kword is None, "unexpected kword: %r" % (kword,)

            e, token, offset = parsemakesyntax(d, offset, varsettokens + ('::', ':'), itermakefilechars)
            if token is None:
                v = e.resolve(makefile, makefile.variables)
                if v.strip() != '':
                    raise SyntaxError("Bad syntax: non-empty line is not a variable assignment or rule.", loc=d.getloc(0))
                continue

            # if we encountered real makefile syntax, the current rule is over
            currule = None

            if token in varsettokens:
                e.lstrip()
                e.rstrip()
                vname = e.resolve(makefile, makefile.variables)
                setvariable(makefile.variables, makefile.variables, makefile,
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
                targets = data.splitwords(e.resolve(makefile, makefile.variables))
                targets = [data.Pattern(p) for p in expandwildcards(makefile, targets)]

                if len(targets):
                    ispatterns = set((t.ispattern() for t in targets))
                    if len(ispatterns) == 2:
                        raise SyntaxError("Mixed implicit and normal rule", d.getloc(offset))
                    ispattern, = ispatterns
                else:
                    ispattern = False

                e, token, offset = parsemakesyntax(d, offset,
                                                   varsettokens + (':', '|', ';'),
                                                   itermakefilechars)
                if token in (None, ';'):
                    prereqs = [p for p in expandwildcards(makefile, data.splitwords(e.resolve(makefile, makefile.variables)))]
                    if ispattern:
                        currule = data.PatternRule(targets, map(data.Pattern, prereqs), doublecolon, loc=d.getloc(0))
                        makefile.appendimplicitrule(currule)
                    else:
                        currule = data.Rule(prereqs, doublecolon, loc=d.getloc(0))
                        for t in targets:
                            makefile.gettarget(t.gettarget()).addrule(currule)
                        if len(targets):
                            makefile.foundtarget(targets[0].gettarget())

                    if token == ';':
                        offset = d.skipwhitespace(offset)
                        e, t, offset = parsemakesyntax(d, offset, (), itercommandchars)
                        currule.addcommand(e)
                elif token in varsettokens:
                    e.lstrip()
                    e.rstrip()
                    vname = e.resolve(makefile, makefile.variables)
                    if ispattern:
                        for target in targets:
                            setvariable(makefile.variables,
                                        makefile.getpatternvariables(target), makefile, vname,
                                        token, d, offset)
                    else:
                        for target in targets:
                            setvariable(makefile.variables,
                                        makefile.gettarget(target.gettarget()).variables, makefile,
                                        vname, token, d, offset)
                elif token == '|':
                    raise NotImplementedError('order-only prerequisites not implemented')
                else:
                    assert token == ':'

                    # static pattern rule
                    if ispattern:
                        raise SyntaxError("static pattern rules must have static targets", d.getloc(0))

                    patstr = e.resolve(makefile, makefile.variables)
                    patterns = data.splitwords(patstr)
                    if len(patterns) != 1:
                        raise SyntaxError("A static pattern rule may have only one pattern", d.getloc(offset))

                    pattern = data.Pattern(patterns[0])

                    e, token, offset = parsemakesyntax(d, offset, (';',), itermakefilechars)
                    prereqs = [data.Pattern(p) for p in expandwildcards(makefile, data.splitwords(e.resolve(makefile, makefile.variables)))]
                    currule = data.PatternRule([pattern], prereqs, doublecolon, loc=d.getloc(0))

                    for t in targets:
                        tname = t.gettarget()
                        stem = pattern.match(tname)
                        if stem is None:
                            raise SyntaxError("Target '%s' of static pattern rule does not match pattern '%s'" % (tname, pattern), d.getloc(0))
                        pinstance = data.PatternRuleInstance(currule, '', stem, pattern.ismatchany())
                        makefile.gettarget(tname).addrule(pinstance)

                    if len(targets):
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
    def __init__(self, parsestate, expansion, tokenlist, closebrace, **kwargs):
        self.parsestate = parsestate
        self.expansion = expansion
        self.tokenlist = tokenlist
        self.closebrace = closebrace
        for key, value in kwargs.iteritems():
            setattr(self, key, value)

functiontokens = list(functions.functionmap.iterkeys())
functiontokens.sort(key=len, reverse=True)
functiontokenlist = TokenList.get(tuple(functiontokens))

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
        ParseStackFrame(PARSESTATE_TOPLEVEL, data.Expansion(loc=d.getloc(startat)),
                        tokenlist=TokenList.get(stopon + ('$',)),
                        stopon=stopon, closebrace=None)
    ]

    di = iterfunc(d, startat, stack[-1].tokenlist)
    while True: # this is not a for loop because `di` changes during the function
        stacktop = stack[-1]
        try:
            s, token, tokenoffset, offset = di.next()
        except StopIteration:
            break

        stacktop.expansion.append(s)
        if token is None:
            continue

        if token == '$':
            if len(d.data) == offset:
                # an unterminated $ expands to nothing
                break

            loc = d.getloc(tokenoffset)

            c = d.data[offset]
            if c == '$':
                stacktop.expansion.append('$')
                offset = offset + 1
            elif c in ('(', '{'):
                closebrace = c == '(' and ')' or '}'

                # look forward for a function name
                fname, offset = d.findtoken(offset + 1, functiontokenlist, True)
                if fname is not None:
                    fn = functions.functionmap[fname](loc)
                    e = data.Expansion()
                    fn.append(e)
                    if len(fn) == fn.maxargs:
                        tokenlist = TokenList.get((closebrace, '$'))
                    else:
                        tokenlist = TokenList.get((',', closebrace, '$'))

                    stack.append(ParseStackFrame(PARSESTATE_FUNCTION,
                                                 e, tokenlist, function=fn,
                                                 closebrace=closebrace))
                    di = iterfunc(d, offset, tokenlist)
                    continue

                e = data.Expansion()
                tokenlist = TokenList.get((':', closebrace, '$'))
                stack.append(ParseStackFrame(PARSESTATE_VARNAME, e, tokenlist, closebrace=closebrace, loc=loc))
                di = iterfunc(d, offset, tokenlist)
                continue
            else:
                e = data.Expansion.fromstring(c)
                stacktop.expansion.append(functions.VariableRef(loc, e))
                offset += 1
        elif stacktop.parsestate == PARSESTATE_TOPLEVEL:
            assert len(stack) == 1
            return stacktop.expansion, token, offset
        elif stacktop.parsestate == PARSESTATE_FUNCTION:
            if token == ',':
                stacktop.expansion = data.Expansion()
                stacktop.function.append(stacktop.expansion)

                if len(stacktop.function) == stacktop.function.maxargs:
                    tokenlist = TokenList.get((stacktop.closebrace, '$'))
                    stacktop.tokenlist = tokenlist
            elif token in (')', '}'):
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
                stacktop.tokenlist = TokenList.get(('=', stacktop.closebrace, '$'))
            elif token in (')', '}'):
                stack.pop()
                stack[-1].expansion.append(functions.VariableRef(stacktop.loc, stacktop.expansion))
            else:
                assert False, "Not reached, PARSESTATE_VARNAME"
        elif stacktop.parsestate == PARSESTATE_SUBSTFROM:
            if token == '=':
                stacktop.substfrom = stacktop.expansion
                stacktop.parsestate = PARSESTATE_SUBSTTO
                stacktop.expansion = data.Expansion()
                stacktop.tokenlist = TokenList.get((stacktop.closebrace, '$'))
            elif token in (')', '}'):
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
            assert token in  (')','}'), "Not reached, PARSESTATE_SUBSTTO"

            stack.pop()
            stack[-1].expansion.append(functions.SubstitutionRef(stacktop.loc, stacktop.varname,
                                                                 stacktop.substfrom, stacktop.expansion))
        else:
            assert False, "Unexpected parse state %s" % stacktop.parsestate

        di = iterfunc(d, offset, stack[-1].tokenlist)

    if len(stack) != 1:
        raise SyntaxError("Unterminated function call", d.getloc(offset))

    assert stack[0].parsestate == PARSESTATE_TOPLEVEL

    return stack[0].expansion, None, None
