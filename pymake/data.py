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

def getpatsubst(substfrom, substto):
    """Given two strings %.from %.to, create regular expression search and
    replace strings."""

    fromprefix, frompercent, fromsuffix = substfrom.partition('%')
    toprefix, topercent, tosuffix = substto.partition('%')

    search = r'^%s%s%s$' % (re.escape(fromprefix),
                            frompercent == '%' and '(.*)' or '',
                            re.escape(fromsuffix))
    replace = r'%s%s%s' % (toprefix.replace('\\', '\\\\'),
                           frompercent == '%' and r'\g<1>' or topercent,
                           tosuffix.replace('\\', '\\\\'))
    return search, replace

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
        substto = self.substto.resolve(variables.setting)

        flavor, source, value = variables.get(vname)
        if value is None:
            log.warning("%s: variable '%s' has no value" % (self.loc, vname))
            return ''

        evalue = value.resolve(variables, setting)
        words = splitwords(evalue)
        if substfrom.find('%') == -1:
            substfrom = "%" + substfrom
            substto = "%" + substto

        search, replace = getpatsubst(substfrom, substto)

        searchre = re.compile(search)
        return " ".join((searchre.sub(word, replace)
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
        self.type = type
        self.rules = []

    def addrule(self, rule):
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

    def set(name, flavor, source, value):
        if not flavor in (FLAVOR_RECURSIVE, FLAVOR_SIMPLE):
            raise DataError("Unexpected variable flavor: %s" % (flavor,))

        if not source in (SOURCE_OVERRIDE, SOURCE_MAKEFILE, SOURCE_AUTOMATIC):
            raise DataError("Unexpected variable source: %s" % (source,))

        if not isinstance(value, Expansion):
            raise DataError("Unexpected variable value, wasn't an expansion.")

        prevflavor, prevsource, prevvalue = self.get(name)
        if prevsource is not None and source > prevsource:
            # TODO: give a location for this warning
            log.warning("not setting variable '%s', set by higher-priority source to value '%s'" % (name, prevvalue))
            return

        self._map[name] = (flavor, source, value)

class Rule(object):
    """
    A rule contains a target and a list of prerequisites. It may also
    contain rule-specific variables.
    """

    RULE_ORDINARY = 0
    RULE_DOUBLECOLON = 1

    def __init__(self, target, makefile):
        self.target = target
        self._prerequisites = []
        self.variables = Variables(parent=makefile.variables)
        self.commands = []

    def addprerequisite(self, d):
        self._prerequisites.append(d)

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

    def addRule(self, rule):
        self._rules.append(rule)
        # TODO: add this to targets!
