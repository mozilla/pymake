"""
Makefile functions.
"""

from pymake import data

log = data.log

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
        assert isinstance(arg, data.Expansion)
        self._arguments.append(arg)

    def expectargs(self, argc):
        if len(self._arguments) < argc:
            raise DataError("Not enough arguments to function %s" % self.name, self.loc)
        if len(self._arguments) > argc:
            log.warning("%s: %s function takes three arguments, got %i" % (self.loc, self.name, len(self._arguments)))

class VariableRef(Function):
    def __init__(self, loc, vname):
        self.loc = loc
        assert isinstance(vname, data.Expansion)
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
        words = data.splitwords(evalue)

        f = data.Pattern(substfrom)
        if not f.ispattern():
            f = data.Pattern('%' + substfrom)
            substto = '%' + substto

        return " ".join((f.subst(substto, word, False)
                         for word in words))

class SubstFunction(Function):
    name = 'subst'

    def setup(self):
        self.expectargs(3)

    def resolve(self, variables, setting):
        s = self._arguments[0].resolve(variables, setting)
        r = self._arguments[1].resolve(variables, setting)
        d = self._arguments[2].resolve(variables, setting)
        return d.replace(s, r)

class PatSubstFunction(Function):
    name = 'patsubst'

    def setup(self):
        self.expectargs(3)

    def resolve(self, variables, setting):
        s = self._arguments[0].resolve(variables, setting)
        r = self._arguments[1].resolve(variables, setting)
        d = self._arguments[2].resolve(variables, setting)

        p = data.Pattern(s)
        return ' '.join((p.subst(r, word, False)
                         for word in data.splitwords(d)))

class StripFunction(Function):
    name = 'strip'

    def setup(self):
        self.expectargs(1)

    def resolve(self, variables, setting):
        return ' '.join(data.splitwords(self._arguments[0].resolve(variables, setting)))

class FindstringFunction(Function):
    name = 'findstring'

    def setup(self):
        self.expectargs(2)

    def resolve(self, variables, setting):
        s = self._arguments[0].resolve(variables, setting)
        r = self._arguments[1].resolve(variables, setting)
        if r.find(s) == -1:
            return ''
        return s

class FilterFunction(Function):
    name = 'filter'

    def setup(self):
        self.expectargs(2)

    def resolve(self, variables, setting):
        ps = self._arguments[0].resolve(variables, setting)
        d = self._arguments[1].resolve(variables.setting)
        plist = [data.Pattern(p) for p in ps]
        r = []
        for w in data.splitwords(d):
            for p in plist:
                if p.match(w) is not None:
                    r.append(w)
                    break

        return ' '.join(r)

class FilteroutFunction(Function):
    name = 'filter-out'

    def setup(self):
        self.expectargs(2)

    def resolve(self, variables, setting):
        ps = self._arguments[0].resolve(variables, setting)
        d = self._arguments[1].resolve(variables, setting)
        plist = [data.Pattern(p) for p in ps]
        r = []
        for w in data.splitwords(d):
            for p in plist:
                if p.match(w) is not None:
                    break
                r.append(w)

        return ' '.join(r)

class SortFunction(Function):
    name = 'sort'

    def setup(self):
        self.expectargs(1)

    def resolve(self, variables, setting):
        d = self._arguments[0].resolve(variables, setting)
        w = data.splitwords(w)
        w.sort()
        return data.withoutdups(w)

class WordFunction(Function):
    name = 'word'

    def setup(self):
        self.expectargs(2)

    def resolve(self, variables, setting):
        n = self._arguments[0].resolve(variables, setting)
        # TODO: provide better error if this doesn't convert
        n = int(n)
        words = data.splitwords(self._arguments[1].resolve(variables, setting))
        if n < 1 or n > len(words):
            return ''
        return words[n - 1]

class WordlistFunction(Function):
    name = 'wordlist'

    def setup(self):
        self.expectargs(3)

    def resolve(self, variables, setting):
        nfrom = self._arguments[0].resolve(variables, setting)
        nto = self._arguments[1].resolve(variables, setting)
        # TODO: provide better errors if this doesn't convert
        nfrom = int(nfrom)
        nto = int(nto)

        words = data.splitwords(self._arguments[2].resolve(variables, setting))

        if nfrom < 1:
            nfrom = 1
        if nto < 1:
            nto = 1

        return ' '.join(words[nfrom - 1:nto])

class FlavorFunction(Function):
    name = 'flavor'

    def setup(self):
        self.expectargs(1)

    def resolve(self, variables, setting):
        varname = self._arguments[0].resolve(variables, setting)

        
        flavor, source, value = variables.get(varname)
        if flavor is None:
            return 'undefined'

        if flavor == data.Variables.FLAVOR_RECURSIVE:
            return 'recursive'
        elif flavor == data.Variables.FLAVOR_SIMPLE:
            return 'simple'

        assert False, "Neither simple nor recursive?"

functionmap = {
    'subst': SubstFunction,
    'patsubst': PatSubstFunction,
    'strip': StripFunction,
    'findstring': FindstringFunction,
    'filter': FilterFunction,
    'filter-out': FilteroutFunction,
    'sort': SortFunction,
    'word': WordFunction,
    'wordlist': WordlistFunction,
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

