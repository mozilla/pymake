#!/usr/bin/env python

"""
A representation of makefile data structures.
"""

import logging, re

log = logging.getLogger('pymake.data')

class DataError(Exception):
    def __init__(self, message, loc=None):
        self.message = message
        self.loc = loc

    def __str__(self):
        return "%s: %s" % (self.loc and self.loc or "internal error",
                           self.message)

class Function(object):
    """
    An object that represents a function call. This class is always subclassed
    with the following two methods:

    def setup(self)
        validates the number of arguments to a function
        no return value
    def resolve(self, variables, setting)
        Calls the function
        @returns string
    """
    def __init__(self, loc):
        self._arguments = []

    def __getitem__(self, key):
        return self._arguments[key]

    def append(self, arg):
        assert(isinstance(arg, Expansion))
        self._arguments.append(arg)

class VariableRef(Function):
    def __init__(self, loc, vname):
        self.loc = loc
        assert(isinstance(vname, Expansion))
        self.vname = vname
        
    def setup(self):
        pass

    def resolve(self, variables, setting):
        vname = self.vname.resolve(variables, setting)
        if vname == setting:
            raise DataError("Setting variable '%s' recursively references itself." % (vname,), self.loc)

        flavor, source, value = variables.get(vname)
        if value is None:
            log.warning("%s: variable '%s' has no value" % (self.loc, vname))
            return ''

        return value.resolve(variables, setting)

_ws = re.compile(r'\s+')

def splitwords(s):
    """Split string s into words delimited by whitespace."""

    words = _ws.split(s)
    for i in (0, -1):
        if words[i] == '':
            del words[i]
    return words

class SubstitutionRef(Function):
    """$(VARNAME:.c=.o) and $(VARNAME:%.c=%.o)"""
    def __init__(self, loc, varname, substfrom, substto):
        self.loc = loc
        self.vname = varname
        self.substfrom = substfrom
        self.substto = substto

    def setup(self):
        pass

    def resolve(self, variables, setting):
        vname = self.vname.resolve(variables, setting)
        if vname == setting:
            raise DataError("Setting variable '%s' recursively references itself." % (vname,), self.loc)

        substfrom = self.substfrom.resolve(variables, setting)
        substto = self.substto.resolve(variables, setting)

        flavor, source, value = variables.get(vname)
        if value is None:
            log.warning("%s: variable '%s' has no value" % (self.loc, vname))
            return ''

        evalue = value.resolve(variables, setting)
        words = splitwords(evalue)

        f = Pattern(substfrom)
        if not f.ispattern():
            f = Pattern('%' + substfrom)
            substto = '%' + substto

        return " ".join((f.subst(substto, word, False)
                         for word in words))

class PatSubstFunction(Function):
    def setup(self):
        if len(self._arguments) < 3:
            raise DataError("Not enough arguments for patsubst", self.loc)
        if len(self._arguments) > 3:
            log.warning("%s: patsubst function takes three arguments, got %i" % (self.loc, len(self._arguments)))

    def resolve(self, variables, setting):
        raise NotImplementedError()

class FlavorFunction(Function):
    def setup(self):
        if len(self._arguments) < 1:
            raise SomeError
        if len(self._arguments) > 1:
            log.warning("%s: flavor function takes one argument, got %i" % (self.loc, len(self._arguments)))

    def resolve(self, variables, setting):
        varname = self._arguments[0].resolve(variables, setting)

        
        flavor, source, value = variables.get(varname, None)
        if flavor is None:
            return 'undefined'

        if flavor == Variables.FLAVOR_RECURSIVE:
            return 'recursive'
        elif flavor == Variables.FLAVOR_SIMPLE:
            return 'simple'

        raise DataError('Variable %s flavor is neither simple nor recursive!' % (varname,))

functions = {
    'subst': None,
    'patsubst': None,
    'strip': None,
    'findstring': None,
    'filter': None,
    'filter-out': None,
    'sort': None,
    'word': None,
    'wordlist': None,
    'words': None,
    'firstword': None,
    'lastword': None,
    'dir': None,
    'notdir': None,
    'suffix': None,
    'basename': None,
    'addsuffix': None,
    'addprefix': None,
    'join': None,
    'wildcard': None,
    'realpath': None,
    'abspath': None,
    'if': None,
    'or': None,
    'and': None,
    'foreach': None,
    'call': None,
    'value': None,
    'eval': None,
    'origin': None,
    'flavor': FlavorFunction,
    'shell': None,
    'error': None,
    'warning': None,
    'info': None,
}

class Expansion(object):
    """
    A representation of expanded data, such as that for a recursively-expanded variable, a command, etc.
    """

    def __init__(self):
        # Each element is either a string or a function
        self._elements = []

    def append(self, object):
        if not isinstance(object, (str, Function)):
            raise DataError("Expansions can contain only strings or functions, got %s" % (type(object),))

        if len(self._elements) and isinstance(object, str) and isinstance(self._elements[-1], str):
            self._elements[-1] += object
        else:
            self._elements.append(object)

    def concat(self, e):
        """Concatenate the other expansion on to this one."""
        for i in e:
            self.append(i)

    def resolve(self, variables, setting):
        """
        Resolve this variable into a value, by interpolating the value
        of other variables.

        @param setting (Variable instance) the variable currently
               being set, if any. Setting variables must avoid self-referential
               loops.
        """
        return ''.join( (isinstance(i, str) and i or i.resolve(variables, setting)
                         for i in self) )

    def __len__(self):
        return len(self._elements)

    def __getitem__(self, key):
        return self._elements[key]

    def __iter__(self):
        return iter(self._elements)

class Target(object):
    """
    A target is a file or arbitrary string. It contains a list of Rules.

    Note: a target may contain a pattern Rule.
    """

    def __init__(self, name):
        self.name = name
        self.rules = []

    def addrule(self, rule):
        if len(rules) and rule.doublecolon != rules[0].doublecolon:
            raise DataError("Cannot have single- and double-colon rules for the same target.")
        rules.append(rule)
        # TODO: sanity-check that the rule either has the name of the target,
        # or that the pattern matches. Also maybe that the type matches

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

    def match(self, word):
        """
        Match this search pattern against a word (string).

        @returns None if the word doesn't match, or the matching stem. If this is a %-less pattern,
                      the stem will always be ''
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

class Rule(object):
    """
    A rule contains a list of prerequisites and a list of commands. It may also
    contain rule-specific variables.
    """

    def __init__(self, target, prereqs, makefile, doublecolon):
        self._prerequisites = [prereqs]
        self.doublecolon = doublecolon
        self.variables = Variables(parent=makefile.variables)
        self.commands = []

    def addprerequisites(self, d):
        self._prerequisites.extend(d)

    def addcommand(self, c):
        """Append a command. Each command must be an Expansion."""
        assert(isinstance(c, Expansion))
        commands.append(c)

class Makefile(object):
    """
    A Makefile is a variable dict, a target dict, and a list of the rules and pattern rules.
    """

    def __init__(self):
        self._targets = {}
        self.variables = Variables()
        self._rules = []

    def addrule(self, rule):
        self._rules.append(rule)
        # TODO: add this to targets!

    def gettarget(self, target):
        return self._targets.setdefault(target, Target(target))

