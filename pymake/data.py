"""
A representation of makefile data structures.
"""

import logging, re, os, subprocess
import pymake

log = logging.getLogger('pymake.data')

class DataError(Exception):
    def __init__(self, message, loc=None):
        self.message = message
        self.loc = loc

    def __str__(self):
        return "%s: %s" % (self.loc and self.loc or "internal error",
                           self.message)

class ResolutionError(DataError):
    """
    Raised when dependency resolution fails, either due to recursion or to missing
    prerequisites.This is separately catchable so that implicit rule search can try things
    without having to commit.
    """
    pass

def withoutdups(it):
    r = set()
    for i in it:
        if not i in r:
            r.add(i)
            yield i

def mtimeislater(deptime, targettime):
    """
    Is the mtime of the dependency later than the target?
    """

    if deptime is None:
        return True
    if targettime is None:
        return False
    return deptime > targettime

def getmtime(path):
    try:
        s = os.stat(path)
        return s.st_mtime
    except OSError:
        return None

_ws = re.compile(r'\s+')

def splitwords(s):
    """Split string s into words delimited by whitespace."""

    words = _ws.split(s)
    for i in (0, -1):
        if len(words) == 0:
            break
        if words[i] == '':
            del words[i]
    return words

def _if_else(c, t, f):
    if c:
        return t()
    return f()

class Expansion(object):
    """
    A representation of expanded data, such as that for a recursively-expanded variable, a command, etc.
    """

    def __init__(self):
        # Each element is either a string or a function
        self._elements = []

    @staticmethod
    def fromstring(s):
        e = Expansion()
        e.append(s)
        return e

    def append(self, object):
        if not isinstance(object, (str, pymake.functions.Function)):
            raise DataError("Expansions can contain only strings or functions, got %s" % (type(object),))

        if len(self) and isinstance(object, str) and isinstance(self[-1], str):
            self[-1] += object
        else:
            self._elements.append(object)

    def concat(self, o):
        """Concatenate the other expansion on to this one."""
        if len(self) > 0 and len(o) > 0 and isinstance(self[-1], str) and isinstance(o[0], str):
            self[-1] += o[0]
            self._elements.extend(o[1:])
        else:
            self._elements.extend(o)

    def lstrip(self):
        """Strip leading literal whitespace from this expansion."""
        if len(self) > 0 and isinstance(self[0], str):
            assert len(self) == 1 or not isinstance(self[1], str), "Strings didn't fold"
            self[0] = self[0].lstrip()

    def rstrip(self):
        """Strip trailing literal whitespace from this expansion."""
        if len(self) > 0 and isinstance(self[-1], str):
            assert len(self) == 1 or not isinstance(self[-2], str), "Strings didn't fold"
            self[-1] = self[-1].rstrip()

    def trimlastnewline(self):
        """Strip only the last newline, if present."""
        if len(self) > 0 and isinstance(self[-1], str) and self[-1][-1] == '\n':
            self[-1] = self[-1][:-1]

    def resolve(self, variables, setting):
        """
        Resolve this variable into a value, by interpolating the value
        of other variables.

        @param setting (Variable instance) the variable currently
               being set, if any. Setting variables must avoid self-referential
               loops.
        """
        return ''.join( (_if_else(isinstance(i, str), lambda: i, lambda: i.resolve(variables, setting))
                         for i in self._elements) )

    def __len__(self):
        return len(self._elements)

    def __getitem__(self, key):
        return self._elements[key]

    def __setitem__(self, key, v):
        self._elements[key] = v

    def __iter__(self):
        return iter(self._elements)

    def __repr__(self):
        return "<Expansion with elements: %r>" % (self._elements,)

class Variables(object):
    """
    A mapping from variable names to variables. Variables have flavor, source, and value. The value is an 
    expansion object.
    """

    FLAVOR_RECURSIVE = 0
    FLAVOR_SIMPLE = 1
    FLAVOR_APPEND = 2

    SOURCE_OVERRIDE = 0
    SOURCE_COMMANDLINE = 1
    SOURCE_MAKEFILE = 2
    # I have no intention of supporting values from the environment
    # SOURCE ENVIRONMENT = 3
    SOURCE_AUTOMATIC = 4
    # I have no intention of supporting builtin rules or variables that go with them
    # SOURCE_IMPLICIT = 5

    def __init__(self, parent=None):
        self._map = {}
        self.parent = parent

    def get(self, name, expand=True):
        """
        Get the value of a named variable. Returns a tuple (flavor, source, value)

        If the variable is not present, returns (None, None, None)

        @param expand If true, the value will be returned as an expansion. If false,
        it will be returned as an unexpanded string.
        """
        if name in self._map:
            flavor, source, valuestr = self._map[name]
            if flavor == self.FLAVOR_APPEND:
                if self.parent:
                    pflavor, psource, pvalue = self.parent.get(name, expand)
                else:
                    pflavor, psource, pvalue = None, None, None

                if pvalue is None:
                    flavor = self.FLAVOR_RECURSIVE
                    # fall through
                else:
                    if source > psource:
                        # TODO: log a warning?
                        return pflavor, psource, pvalue

                    if not expand:
                        return pflavor, psource, pvalue + ' ' + valuestr

                    d = pymake.parser.Data(None, None)
                    d.append(valuestr, pymake.parser.Location("Expansion of variable '%s'" % (name,), 1, 0))
                    appende, t, o = pymake.parser.parsemakesyntax(d, 0, (), pymake.parser.iterdata)

                    pvalue.append(' ')
                    pvalue.concat(appende)

                    return pflavor, psource, pvalue
                    
            if not expand:
                return flavor, source, valuestr

            if flavor == self.FLAVOR_RECURSIVE:
                d = pymake.parser.Data(None, None)
                d.append(valuestr, pymake.parser.Location("Expansion of variable '%s'" % (name,), 1, 0))
                val, t, o = pymake.parser.parsemakesyntax(d, 0, (), pymake.parser.iterdata)
            else:
                val = Expansion.fromstring(valuestr)

            return flavor, source, val

        if self.parent is not None:
            return self.parent.get(name, expand)

        return (None, None, None)

    def set(self, name, flavor, source, value):
        assert flavor in (self.FLAVOR_RECURSIVE, self.FLAVOR_SIMPLE)
        assert source in (self.SOURCE_OVERRIDE, self.SOURCE_COMMANDLINE, self.SOURCE_MAKEFILE, self.SOURCE_AUTOMATIC)
        assert isinstance(value, str)

        prevflavor, prevsource, prevvalue = self.get(name)
        if prevsource is not None and source > prevsource:
            # TODO: give a location for this warning
            log.warning("not setting variable '%s', set by higher-priority source to value '%s'" % (name, prevvalue))
            return

        self._map[name] = (flavor, source, value)

    def append(self, name, source, value, variables):
        assert source in (self.SOURCE_OVERRIDE, self.SOURCE_MAKEFILE, self.SOURCE_AUTOMATIC)
        assert isinstance(value, str)
        
        if name in self._map:
            prevflavor, prevsource, prevvalue = self._map[name]
            if source > prevsource:
                # TODO: log a warning?
                return

            if prevflavor == self.FLAVOR_SIMPLE:
                d = pymake.parser.Data(None, None)
                d.append(value, pymake.parser.Location("Expansion of variable '%s'" % (name,), 1, 0))
                e, t, o = pymake.parser.parsemakesyntax(d, 0, (), pymake.parser.iterdata)
                val = e.resolve(variables, name)
            else:
                val = value

            self._map[name] = prevflavor, prevsource, prevvalue + ' ' + val
        else:
            self._map[name] = self.FLAVOR_APPEND, source, value

    def merge(self, other):
        assert isinstance(other, Variables)
        for k, flavor, source, value in other:
            self.set(k, flavor, source, value)

    def __iter__(self):
        for k, (flavor, source, value) in self._map.iteritems():
            yield k, flavor, source, value

    def __contains__(self, item):
        return item in self._map

class Pattern(object):
    """
    A pattern is a string, possibly with a % substitution character. From the GNU make manual:

    '%' characters in pattern rules can be quoted with precending backslashes ('\'). Backslashes that
    would otherwise quote '%' charcters can be quoted with more backslashes. Backslashes that
    quote '%' characters or other backslashes are removed from the pattern before it is compared t
    file names or has a stem substituted into it. Backslashes that are not in danger of quoting '%'
    characters go unmolested. For example, the pattern the\%weird\\%pattern\\ has `the%weird\' preceding
    the operative '%' character, and 'pattern\\' following it. The final two backslashes are left alone
    because they cannot affect any '%' character.

    This insane behavior probably doesn't matter, but we're compatible just for shits and giggles.
    """

    def __init__(self, s):
        r = []
        i = 0
        while i < len(s):
            c = s[i]
            if c == '\\':
                nc = s[i + 1]
                if nc == '%':
                    r.append('%')
                    i += 1
                elif nc == '\\':
                    r.append('\\')
                    i += 1
                else:
                    r.append(c)
            elif c == '%':
                self.data = (''.join(r), s[i+1:])
                return
            else:
                r.append(c)
            i += 1

        # This is different than (s,) because \% and \\ have been unescaped. Parsing patterns is
        # context-sensitive!
        self.data = (''.join(r),)

    def ismatchany(self):
        return self.data == ('','')

    def ispattern(self):
        return len(self.data) == 2

    def __hash__(self):
        return self.data.__hash__()

    def __eq__(self, o):
        assert isinstance(o, Pattern)
        return self.data == o.data

    def gettarget(self):
        assert not self.ispattern()
        return self.data[0]

    def hasslash(self):
        return self.data[0].find('/') != -1 or self.data[1].find('/') != -1

    def match(self, word):
        """
        Match this search pattern against a word (string).

        @returns None if the word doesn't match, or the matching stem.
                      If this is a %-less pattern, the stem will always be ''
        """
        if self.ispattern():
            search = r'^%s(.*)%s$' % (re.escape(self.data[0]),
                                      re.escape(self.data[1]))
        else:
            search = r'^%s()$' % (re.escape(self.data[0]),)

        m = re.match(search, word)
        if m is None:
            return None
        return m.group(1)

    def resolve(self, dir, stem):
        if self.ispattern():
            return dir + self.data[0] + stem + self.data[1]

        return self.data[0]

    def subst(self, replacement, word, mustmatch):
        """
        Given a word, replace the current pattern with the replacement pattern, a la 'patsubst'

        @param mustmatch If true and this pattern doesn't match the word, throw a DataError. Otherwise
                         return word unchanged.
        """
        assert isinstance(replacement, str)

        stem = self.match(word)
        if stem is None:
            if mustmatch:
                raise DataError("target '%s' doesn't match pattern" % (word,))
            return word

        if not self.ispattern():
            # if we're not a pattern, the replacement is not parsed as a pattern either
            return replacement

        return Pattern(replacement).resolve('', stem)

    def __repr__(self):
        return "<Pattern with data %r>" % (self.data,)

class Target(object):
    """
    An actual (non-pattern) target.

    It holds target-specific variables and a list of rules. It may also point to a parent
    PatternTarget, if this target is being created by an implicit rule.

    The rules associated with this target may be Rule instances or, in the case of static pattern
    rules, PatternRule instances.
    """

    def __init__(self, target, makefile):
        assert isinstance(target, str)
        self.target = target
        self.vpathtarget = None
        self.rules = []
        self.variables = Variables(makefile.variables)
        self.explicit = False

    def addrule(self, rule):
        if len(self.rules) and rule.doublecolon != rules[0].doublecolon:
            # TODO: better location for this error
            raise DataError("Cannot have single- and double-colon rules for the same target.")

        if isinstance(rule, PatternRule):
            if len(rule.targetpatterns) != 1:
                # TODO: better location
                raise DataError("Static pattern rules must only have one target pattern")
            if rule.targetpatterns[0].match(self.target) is None:
                # TODO: better location
                raise DataError("Static pattern rule doesn't match target")

        self.rules.append(rule)

    def isdoublecolon(self):
        return self.rules[0].doublecolon

    def isphony(self, makefile):
        """Is this a phony target? We don't check for existence of phony targets."""
        phony = makefile.gettarget('.PHONY').hasdependency(self.target)

    def hasdependency(self, t):
        for rule in self.rules:
            if t in rule.prerequisites:
                return True

        return False

    def resolveimplicitrule(self, makefile, targetstack, rulestack):
        """
        Try to resolve an implicit rule to build this target.
        """
        # The steps in the GNU make manual Implicit-Rule-Search.html are very detailed. I hope they can be trusted.

        candidates = [r
                      for r in makefile.implicitrules
                      if r.matchfor(self.target) is not None and len(r.commands) > 0]

        if any((r.ismatchany() for r in candidates)):
            candidates = [r
                          for r in candidates
                          if (not r.ismatchany()) or r.doublecolon]

        for r in candidates:
            newrulestack = rulestack + [r]

            depfailed = False
            for p in r.prerequisitesfor(self.target):
                t = makefile.gettarget(p)
                try:
                    t.resolvedeps(makefile, targetstack, newrulestack)
                except ResolutionError:
                    depfailed = True
                    break
                if t.mtime is None and not t.explicit:
                    depfailed = True
                    break

            if depfailed:
                continue

            log.info("Found implicit rule at %s for target '%s'" % (r.loc, self.target))
            self.rules.append(r)
            return

        # eliminate terminal rules
        candidates = [r for r in candidates
                      if not r.doublecolon]

        # Try again, but this time with chaining and love

        for r in candidates:
            newrulestack = rulestack + [r]

            depfailed = False
            for p in r.prerequisitesfor(self.target):
                t = makefile.gettarget(p)
                try:
                    t.resolvedeps(makefile, targetstack, newrulestack)
                except ResolutionError:
                    depfailed = True
                    break

            if depfailed:
                continue

            log.info("Found implicit rule at %s for target '%s'" % (r.loc, self.target))
            self.rules.append(r)
            return

        log.info("Couldn't find implicit rule to remake '%s'" % (self.target,))

    def ruleswithcommands(self):
        "The number of rules with commands"
        return reduce(lambda i, rule: i + (len(rule.commands) > 0), self.rules, 0)

    def resolvedeps(self, makefile, targetstack, rulestack, required=True):
        """
        Resolve the actual path of this target, using vpath if necessary.

        Recursively resolve dependencies of this target. This means finding implicit
        rules which match the target, if appropriate.

        Figure out whether this target needs to be rebuild, and set self.outofdate
        appropriately.

        @param targetstack is the current stack of dependencies being resolved. If
               this target is already in targetstack, bail to prevent infinite
               recursion.
        @param rulestack is the current stack of implicit rules being used to resolve
               dependencies. A rule chain cannot use the same implicit rule twice.
        """
        assert makefile.parsingfinished

        if self.target in targetstack:
            raise ResolutionError("Recursive dependency: %s -> %s" % (
                    " -> ".join(targetstack), self.target))

        targetstack = targetstack + [self.target]

        self.resolvevpath(makefile)

        # self.remade is a tri-state:
        #   None - we haven't remade yet
        #   True - we did something to remake ourself
        #   False - we did nothing to remake ourself
        self.remade = None

        # Sanity-check our rules. If we're single-colon, only one rule should have commands
        ruleswithcommands = self.ruleswithcommands()
        if len(self.rules) and not self.isdoublecolon():
            if ruleswithcommands > 1:
                # In GNU make this is a warning, not an error. I'm going to be stricter.
                # TODO: provide locations
                raise DataError("Target '%s' has multiple rules with commands." % self.target)

        if ruleswithcommands == 0:
            found = self.resolveimplicitrule(makefile, targetstack, rulestack)

        # If a target is mentioned, but doesn't exist, has no commands and no
        # prerequisites, it is special and exists just to say that targets which
        # depend on it are always out of date. This is like .FORCE but more
        # compatible with other makes.
        # Otherwise, we don't know how to make it.
        if not len(self.rules) and self.mtime is None and not any((len(rule.prerequisitesfor(self.target)) > 0
                                                                   for rule in self.rules)):
            if required:
                raise ResolutionError("No rule to make %s needed by %s" % (self.target,
                    ' -> '.join(targetstack[:-1])))

        for r in self.rules:
            newrulestack = rulestack + [r]
            for d in r.prerequisitesfor(self.target):
                makefile.gettarget(d).resolvedeps(makefile, targetstack, newrulestack)

        for v in makefile.getpatternvariablesfor(self.target):
            self.variables.merge(v)

    def resolvevpath(self, makefile):
        if self.isphony(makefile):
            self.vpathtarget = self.target
            self.mtime = None

        if self.vpathtarget is None:
            search = [self.target]
            if not os.path.isabs(self.target):
                search += [os.path.join(dir, self.target)
                           for dir in makefile.vpath]

            for t in search:
                mtime = getmtime(t)
                if mtime is not None:
                    self.vpathtarget = t
                    self.mtime = mtime
                    return

            self.vpathtarget = self.target
            self.mtime = None
        
    def remake(self):
        """
        When we remake ourself, we need to reset our mtime and vpathtarget
        """
        self.mtime = None
        self.vpathtarget = self.target

    def make(self, makefile):
        """
        If we are out of date, make ourself.

        For now, making is synchronous/serialized. -j magic will come later.

        @returns True if anything was done to remake this target
        """
        assert self.vpathtarget is not None, "Target was never resolved!"

        if self.remade is not None:
            return self.remade

        didanything = False

        if len(self.rules) == 0:
            assert self.mtime is not None
        elif self.isdoublecolon():
            for r in self.rules:
                remake = False
                if self.mtime is None:
                    log.info("Remaking %s using rule at %s because it doesn't exist or is a forced target" % (self.target, r.loc))
                    remake = True
                for p in r.prerequisitesfor(self.target):
                    dep = makefile.gettarget(p)
                    didanything = dep.make(makefile) or didanything
                    if not remake and mtimeislater(dep.mtime, self.mtime):
                        log.info("Remaking %s using rule at %s because %s is newer." % (self.target, r.loc, p))
                        remake = True
                if remake:
                    self.remake()
                    rule.execute(self, makefile)
                    didanything = True
        else:
            commandrule = None
            remake = False
            if self.mtime is None:
                log.info("Remaking %s because it doesn't exist or is a forced target" % (self.target,))
                remake = True

            for r in self.rules:
                if len(r.commands):
                    assert commandrule is None, "Two command rules for a single-colon target?"
                    commandrule = r
                for p in r.prerequisitesfor(self.target):
                    dep = makefile.gettarget(p)
                    didanything = dep.make(makefile) or didanything
                    if not remake and mtimeislater(dep.mtime, self.mtime):
                        log.info("Remaking %s because %s is newer" % (self.target, p))
                        remake = True

            if remake:
                self.remake()
                if commandrule is not None:
                    commandrule.execute(self, makefile)
                didanything = True

        self.remade = didanything
        return didanything

def setautomaticvariables(v, makefile, target, prerequisites):
    vprereqs = [makefile.gettarget(p).vpathtarget
                for p in prerequisites]

    v.set('@', Variables.FLAVOR_SIMPLE, Variables.SOURCE_AUTOMATIC, target.vpathtarget)

    if len(vprereqs):
        v.set('<', Variables.FLAVOR_SIMPLE, Variables.SOURCE_AUTOMATIC, vprereqs[0])

    # TODO '?'
    v.set('^', Variables.FLAVOR_SIMPLE, Variables.SOURCE_AUTOMATIC,
          ' '.join(withoutdups(vprereqs)))
    v.set('+', Variables.FLAVOR_SIMPLE, Variables.SOURCE_AUTOMATIC,
          ' '.join(vprereqs))
    # TODO '|'
    # TODO all the D and F variants

def splitcommand(command):
    """
    Using the esoteric rules, split command lines by unescaped newlines.
    """
    start = 0
    i = 0
    while i < len(command):
        c = command[i]
        if c == '\\':
            i += 1
        elif c == '\n':
            yield command[start:i]
            i += 1
            start = i
            continue

        i += 1

    if i > start:
        yield command[start:i]

class Rule(object):
    """
    A rule contains a list of prerequisites and a list of commands. It may also
    contain rule-specific variables. This rule may be associated with multiple targets.
    """

    def __init__(self, prereqs, doublecolon, loc):
        self.prerequisites = prereqs
        self.doublecolon = doublecolon
        self.commands = []

    def addcommand(self, c):
        """Append a command expansion."""
        assert(isinstance(c, Expansion))
        self.commands.append(c)

    def prerequisitesfor(self, t):
        return self.prerequisites

    def execute(self, target, makefile):
        assert isinstance(target, Target)

        v = Variables(parent=target.variables)
        setautomaticvariables(v, makefile, target, self.prerequisites)
        # TODO: $* in non-pattern rules sucks

        for c in self.commands:
            cstring = c.resolve(v, None)
            for cline in splitcommand(cstring):
                if cline[0:1] == '@':
                    cline = cline[1:]
                if not len(cline) or cline.isspace():
                    continue
                subprocess.check_call(cline, shell=True)

class PatternRule(object):
    """
    An implicit rule or static pattern rule containing target patterns, prerequisite patterns,
    and a list of commands.
    """

    def __init__(self, targetpatterns, prerequisites, doublecolon, loc):
        self.targetpatterns = targetpatterns
        self.prerequisites = prerequisites
        self.doublecolon = doublecolon
        self.loc = loc
        self.commands = []

    def addcommand(self, c):
        assert isinstance(c, Expansion)
        self.commands.append(c)

    def ismatchany(self):
        return any((t.ismatchany() for t in self.targetpatterns))

    def matchfor(self, t):
        """
        Determine whether and how this rule might match target t.
        @returns a tuple (dir, stem) if this rule matches, or None
        """

        for p in self.targetpatterns:
            stem = p.match(t)
            if stem is not None:
                return ('', stem)

        dir, s, path = t.rpartition('/')
        if s == '':
            return None

        for p in self.targetpatterns:
            if p.hasslash():
                continue

            stem = p.match(path)
            if stem is not None:
                return (dir + s, stem)

        return None

    def prerequisitesfor(self, t=None, dir=None, stem=None):
        if stem is None:
            dir, stem = self.matchfor(t)

        return [p.resolve(dir, stem) for p in self.prerequisites]

    def execute(self, target, makefile):
        assert isinstance(target, Target)

        dir, stem = self.matchfor(target.target)

        v = Variables(parent=target.variables)
        setautomaticvariables(v, makefile, target,
                              self.prerequisitesfor(stem=stem, dir=dir))
        v.set('*', Variables.FLAVOR_SIMPLE, Variables.SOURCE_AUTOMATIC, stem)

        for c in self.commands:
            cstring = c.resolve(v, None)
            if cstring[0:1] == '@':
                cstring = cstring[1:]
            subprocess.check_call(cstring, shell=True)

class Makefile(object):
    def __init__(self, workdir=None, restarts=0):
        self.defaulttarget = None
        self.variables = Variables()
        self._targets = {}
        self._patternvariables = [] # of (pattern, variables)
        self.implicitrules = []
        self.parsingfinished = False

        if workdir is None:
            workdir = os.getcwd()
        workdir = os.path.realpath(workdir)
        self.workdir = workdir
        self.variables.set('CURDIR', Variables.FLAVOR_SIMPLE,
                           Variables.SOURCE_AUTOMATIC, workdir)

        # the list of included makefiles, whether or not they existed
        self.included = []

        self.variables.set('MAKE_RESTARTS', Variables.FLAVOR_SIMPLE,
                           Variables.SOURCE_AUTOMATIC, restarts > 0 and str(restarts) or '')

    def foundtarget(self, t):
        """
        Inform the makefile of a target which is a candidate for being the default target,
        if there isn't already a default target.
        """
        if self.defaulttarget is None:
            self.defaulttarget = t

    def getpatternvariables(self, pattern):
        assert isinstance(pattern, Pattern)

        for p, v in self._patternvariables:
            if p == pattern:
                return v

        v = Variables()
        self._patternvariables.append( (pattern, v) )
        return v

    def getpatternvariablesfor(self, target):
        for p, v in self._patternvariables:
            if p.match(target):
                yield v

    def hastarget(self, target):
        return target in self._targets

    def gettarget(self, target):
        assert isinstance(target, str)
        t = self._targets.get(target, None)
        if t is None:
            t = Target(target, self)
            self._targets[target] = t
        return t

    def appendimplicitrule(self, rule):
        assert isinstance(rule, PatternRule)
        self.implicitrules.append(rule)

    def finishparsing(self):
        """
        Various activities, such as "eval", are not allowed after parsing is
        finished. In addition, various warnings and errors can only be issued
        after the parsing data model is complete. All dependency resolution
        and rule execution requires that parsing be finished.
        """
        self.parsingfinished = True

        flavor, source, value = self.variables.get('GPATH')
        if value is not None and value.resolve(self.variables, 'GPATH').strip() != '':
            raise DataError('GPATH was set: pymake does not support GPATH semantics')

        flavor, source, value = self.variables.get('VPATH')
        if value is None:
            self.vpath = []
        else:
            self.vpath = filter(lambda e: e != '', re.split('[:\s]+', value.resolve(self.variables, 'VPATH')))

        targets = list(self._targets.itervalues())
        for t in targets:
            t.explicit = True
            for r in t.rules:
                for p in r.prerequisitesfor(t.target):
                    self.gettarget(p).explicit = True

    def include(self, path, required=True):
        """
        Include the makefile at `path`.
        """
        self.included.append(path)
        if os.path.exists(path):
            fd = open(path)
            self.variables.append('MAKEFILE_LIST', Variables.SOURCE_AUTOMATIC, path, None)
            pymake.parser.parsestream(fd, path, self)
            self.gettarget(path).explicit = True
        elif required:
            raise DataError("Attempting to include file which doesn't exist.")

    def remakemakefiles(self):
        reparse = False

        tlist = [self.gettarget(f) for f in self.included]
        for t in tlist:
            t.explicit = True
            t.resolvedeps(self, [], [], required=False)
        for t in tlist:
            if len(t.rules) > 0:
                oldmtime = t.mtime
                t.make(self)
                if t.mtime != oldmtime:
                    log.info("included makefile '%s' was remade" % t.target)
                    reparse = True

        return reparse
