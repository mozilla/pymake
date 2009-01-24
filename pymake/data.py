#!/usr/bin/env python

"""
A representation of makefile data structures.
"""

import logging

log = logging.getLogger('pymake.data')

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
    def __init__(self):
        self._arguments = []

    def append(self, arg):
        self._arguments.append(arg)

class FlavorFunction(Function):
    def setup(self):
        if len(self._arguments) < 1:
            raise SomeError
        if len(self._arguments) > 1:
            log.warning("Function 'flavor' only takes one argument.")

    def resolve(self, variables, setting):
        varname = self._arguments[0].resolve(variables, setting)

        v = variables.get(varname, None)
        if v is None:
            return 'undefined'

        if v.flavor == Variable.FLAVOR_RECURSIVE:
            return 'recursive'
        elif v.flavor == Variable.FLAVOR_SIMPLE:
            return 'simple'

        raise TODODataError('Variable %s flavor is neither simple nor recursive!' % varname)

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

class Variable(object):
    """
    An object that represents a string with variable substitutions.
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

    def __init__(self, flavor, source):
        self._elements = []

        assert(flavor in (FLAVOR_RECURSIVE, FLAVOR_SIMPLE))
        self.flavor = flavor

        assert(source in (SOURCE_OVERRIDE, SOURCE_MAKEFILE, SOURCE_AUTOMATIC))
        self.source = source

    def append(self, object):
        self._elements.append(object)

    def __iter__(self):
        return iter(self._elements)

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

class Target(object):
    """
    A target is a file or arbitrary string. It contains a list of Rules.

    Note: a target may contain a pattern Rule.
    """

    def __init__(self, name):
        self.name = name
        self.type = type
        self.rules = []

    def addRule(self, rule):
        rules.append(rule)
        # TODO: sanity-check that the rule either has the name of the target,
        # or that the pattern matches. Also maybe that the type matches

class Rule(object):
    """
    A rule contains a target and a list of prerequisites. It may also
    contain rule-specific variables.
    """

    RULE_ORDINARY = 0
    RULE_DOUBLECOLON = 1

    def __init__(self, target):
        self.target = target
        self._dependencies = []
        self._variables = {}

    def adddependency(self, d):
        self._dependencies.append(d)

    def addvariable(self, v, value):
        self._variables[v] = value

class Makefile(object):
    """
    A Makefile is a variable dict, a target dict, and a list of rules.

    TODO: should the rules be *all* the rules, or just the pattern rules?
    """

    def __init__(self):
        self._targets = {}
        self._variables = {}
        self._rules = []

    def setVariable(self, name, value):
        assert(isinstance(value, Variable))

        if name in self._variables:
            oldsource = self._variables[name].source
            if newsource > oldsource:
                log.warning("Not setting variable '%s', already set to higher priority value." % (name, ))
                return

        self._variables[name] = value

    def addRule(self, rule):
        self._rules.append(rule)
        # TODO: add this to targets!
