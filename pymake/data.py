#!/usr/bin/env python

"""
An internal representation of a makefile.
"""

class FunctionCall(object):
    """
    An object that represents a function call. This class is always subclassed
    with a .resolve method which actually performs the function.
    """
    def __init__(self):
        self._arguments = []

    def append(self, arg):
        self._arguments.append(arg)

class Variable(object):
    """
    An object that represents a string with variable substitutions.
    """

    def __init__(self):
        self._elements = []

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

class Rule(object):
    """
    A rule contains a target and a list of prerequisites. It may also
    contain rule-specific variables.

    Note: a PatternRule is not a rule; it's a formula for creating a rule.
    """

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
    A makefile is a series of rules and a set of global variable definitions.
    """

    def __init__(self):
        self._rules = []
        self._variables = {}
