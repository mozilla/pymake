#!/usr/bin/env python

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
    return mt > mto

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

class Variables(object):
    """
    A mapping from variable names to variables. Variables have flavor, source, and value. The value is an 
    expansion object.
    """

    FLAVOR_RECURSIVE = 0
    FLAVOR_SIMPLE = 1

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

    def get(self, name):
        """
        Get the value of a named variable. Returns a tuple (flavor, source, value)

        If the variable is not present, returns (None, None, None)
        """
        v = self._map.get(name, None)
        if v is not None:
            return v

        if self.parent is not None:
            return self.parent.get(name)

        return (None, None, None)

    def set(self, name, flavor, source, value):
        if not flavor in (self.FLAVOR_RECURSIVE, self.FLAVOR_SIMPLE):
            raise DataError("Unexpected variable flavor: %s" % (flavor,))

        if not source in (self.SOURCE_OVERRIDE, self.SOURCE_MAKEFILE, self.SOURCE_AUTOMATIC):
            raise DataError("Unexpected variable source: %s" % (source,))

        if not isinstance(value, Expansion):
            raise DataError("Unexpected variable value, wasn't an expansion.")

        prevflavor, prevsource, prevvalue = self.get(name)
        if prevsource is not None and source > prevsource:
            # TODO: give a location for this warning
            log.warning("not setting variable '%s', set by higher-priority source to value '%s'" % (name, prevvalue))
            return

        self._map[name] = (flavor, source, value)

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

    def resolve(self, stem):
        if self.ispattern():
            return self.data[0] + stem + self.data[1]

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

        return Pattern(replacement).resolve(stem)

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

    def resolvedeps(self, makefile, targetstack, rulestack):
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
            raise DataError("Recursive dependency: %s -> %s" % (
                    " -> ".join(targetstack), self.target))

        targetstack = targetstack + [self.target]

        self.resolvevpath(makefile)

        # Sanity-check our rules. If we're single-colon, only one rule should have commands
        ruleswithcommands = reduce(lambda i, rule: i + len(rule.commands) > 0, self.rules, 0)
        if len(self.rules) and not self.isdoublecolon():
            if ruleswithcommands > 1:
                # In GNU make this is a warning, not an error. I'm going to be stricter.
                # TODO: provide locations
                raise DataError("Target '%s' has multiple rules with commands." % self.target)

        if ruleswithcommands == 0:
            if len(makefile.implicitrules) > 0:
                raise NotImplementedError("No rules to make '%s', and implicit rules aren't implemented yet!" % (self.target,))

        for r in self.rules:
            newrulestack = rulestack + [r]
            for d in r.prerequisitesfor(self.target):
                makefile.gettarget(d).resolvedeps(makefile, targetstack, newrulestack)

    def resolvevpath(self, makefile):
        if self.isphony(makefile):
            self.vpathtarget = self.target
            self.mtime = None

        if self.vpathtarget is None:
            # TODO: the vpath is a figment of your imagination
            self.vpathtarget = self.target
            self.mtime = getmtime(self.target)
        
    def make(self, makefile):
        """
        If we are out of date, make ourself.

        For now, making is synchronous/serialized. -j magic will come later.
        """
        assert self.vpathtarget is not None, "Target was never resolved!"

        if self.isdoublecolon():
            for r in self.rules:
                remake = False
                depcount = 0
                for p in r.prerequisitesfor(self.target):
                    depcount += 1
                    dep = makefile.gettarget(p)
                    dep.make(makefile)
                    if mtimeislater(dep.mtime, self.mtime):
                        remake = True
                if remake or depcount == 0:
                    rule.execute(self, makefile)
        else:
            commandrule = None
            remake = False
            depcount = 0

            for r in self.rules:
                if len(r.commands):
                    assert commandrule is None, "Two command rules for a single-colon target?"
                    commandrule = r
                for p in r.prerequisitesfor(self.target):
                    depcount += 1
                    dep = makefile.gettarget(p)
                    dep.make(makefile)
                    if mtimeislater(dep.mtime, self.mtime):
                        remake = True

            if remake or depcount == 0:
                commandrule.execute(self, makefile)
                
class Rule(object):
    """
    A rule contains a list of prerequisites and a list of commands. It may also
    contain rule-specific variables. This rule may be associated with multiple targets.
    """

    def __init__(self, prereqs, doublecolon):
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
        v.set('@', Variables.FLAVOR_SIMPLE, Variables.SOURCE_AUTOMATIC, Expansion.fromstring(target.target))

        if len(self.prerequisites):
            v.set('<', Variables.FLAVOR_SIMPLE, Variables.SOURCE_AUTOMATIC, Expansion.fromstring(self.prerequisites[0]))

        # TODO '?'
        v.set('^', Variables.FLAVOR_SIMPLE, Variables.SOURCE_AUTOMATIC,
              Expansion.fromstring(' '.join(withoutdups(self.prerequisites))))
        v.set('+', Variables.FLAVOR_SIMPLE, Variables.SOURCE_AUTOMATIC,
              Expansion.fromstring(' '.join(self.prerequisites)))
        # TODO '|'
        # TODO (or not?) $*
        # TODO all the D and F variants

        for c in self.commands:
            cstring = c.resolve(v, None)
            if cstring[0:1] == '@':
                cstring = cstring[1:]
            subprocess.check_call(cstring, shell=True)

class PatternRule(object):
    """
    An implicit rule or static pattern rule containing target patterns, prerequisite patterns,
    and a list of commands.
    """

    def __init__(self, targetpatterns, prerequisites, doublecolon):
        self.targetpatterns = targetpatterns
        self.prerequisites = prerequisites
        self.doublecolon = doublecolon
        self.commands = []

    def addcommand(self, c):
        assert isinstance(c, Expansion)
        self.commands.append(c)

    def prerequisitesfor(self, t):
        raise NotImplementedError()

class Makefile(object):
    def __init__(self):
        self.defaulttarget = None
        self.variables = Variables()
        self._targets = {}
        self._patternvariables = {}
        self.implicitrules = []
        self.parsingfinished = False

    def foundtarget(self, t):
        """
        Inform the makefile of a target which is a candidate for being the default target,
        if there isn't already a default target.
        """
        if self.defaulttarget is None:
            self.defaulttarget = t

    def getpatternvariables(self, pattern):
        assert isinstance(pattern, Pattern)
        return self._patternvariables.setdefault(pattern, Variables())

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
