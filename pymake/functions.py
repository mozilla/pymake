"""
Makefile functions.
"""

from pymake import data
import subprocess, os, glob

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
        self.loc = loc

    def __getitem__(self, key):
        return self._arguments[key]

    def setup(self):
        self.expectargs(self.expectedargs)

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
        assert False, "Shouldn't get here"

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
        assert False, "Shouldn't get here"

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
    expectedargs = 3

    def resolve(self, variables, setting):
        s = self._arguments[0].resolve(variables, setting)
        r = self._arguments[1].resolve(variables, setting)
        d = self._arguments[2].resolve(variables, setting)
        return d.replace(s, r)

class PatSubstFunction(Function):
    name = 'patsubst'
    expectedargs = 3

    def resolve(self, variables, setting):
        s = self._arguments[0].resolve(variables, setting)
        r = self._arguments[1].resolve(variables, setting)
        d = self._arguments[2].resolve(variables, setting)

        p = data.Pattern(s)
        return ' '.join((p.subst(r, word, False)
                         for word in data.splitwords(d)))

class StripFunction(Function):
    name = 'strip'
    expectedargs = 1

    def resolve(self, variables, setting):
        return ' '.join(data.splitwords(self._arguments[0].resolve(variables, setting)))

class FindstringFunction(Function):
    name = 'findstring'
    expectedargs = 2

    def resolve(self, variables, setting):
        s = self._arguments[0].resolve(variables, setting)
        r = self._arguments[1].resolve(variables, setting)
        if r.find(s) == -1:
            return ''
        return s

class FilterFunction(Function):
    name = 'filter'
    expectedargs = 2

    def resolve(self, variables, setting):
        ps = self._arguments[0].resolve(variables, setting)
        d = self._arguments[1].resolve(variables, setting)
        plist = [data.Pattern(p) for p in data.splitwords(ps)]
        r = []
        for w in data.splitwords(d):
            if any((p.match(w) for p in plist)):
                    r.append(w)
                
        return ' '.join(r)

class FilteroutFunction(Function):
    name = 'filter-out'
    expectedargs = 2

    def resolve(self, variables, setting):
        ps = self._arguments[0].resolve(variables, setting)
        d = self._arguments[1].resolve(variables, setting)
        plist = [data.Pattern(p) for p in data.splitwords(ps)]
        r = []
        for w in data.splitwords(d):
            found = False
            if not any((p.match(w) for p in plist)):
                r.append(w)

        return ' '.join(r)

class SortFunction(Function):
    name = 'sort'
    expectedargs = 1

    def resolve(self, variables, setting):
        d = self._arguments[0].resolve(variables, setting)
        w = data.splitwords(d)
        w.sort()
        return ' '.join((w for w in data.withoutdups(w)))

class WordFunction(Function):
    name = 'word'
    expectedargs = 2

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
    expectedargs = 3

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

class WordsFunction(Function):
    name = 'words'
    expectedargs = 1

    def resolve(self, variables, setting):
        return str(len(data.splitwords(self._arguments[0].resolve(variables, setting))))

class FirstWordFunction(Function):
    name = 'firstword'
    expectedargs = 1

    def resolve(self, variables, setting):
        wl = data.splitwords(self._arguments[0].resolve(variables, setting))
        if len(wl) == 0:
            return ''
        return wl[0]

class LastWordFunction(Function):
    name = 'lastword'
    expectedargs = 1

    def resolve(self, variables, setting):
        wl = data.splitwords(self._arguments[0].resolve(variables, setting))
        if len(wl) == 0:
            return ''
        return wl[0]

def pathsplit(path, default='./'):
    """
    Splits a path into dirpart, filepart on the last slash. If there is no slash, dirpart
    is ./
    """
    dir, slash, file = path.rpartition('/')
    if dir == '':
        return default, file

    return dir + slash, file

class DirFunction(Function):
    name = 'dir'
    expectedargs = 1

    def resolve(self, variables, setting):
        return ' '.join((pathsplit(path)[0]
                         for path in data.splitwords(self._arguments[0].resolve(variables, setting))))

class NotDirFunction(Function):
    name = 'notdir'
    expectedargs = 1

    def resolve(self, variables, setting):
        return ' '.join((pathsplit(path)[1]
                         for path in data.splitwords(self._arguments[0].resolve(variables, setting))))

class SuffixFunction(Function):
    name = 'suffix'
    expectedargs = 1

    @staticmethod
    def suffixes(words):
        for w in words:
            dir, file = pathsplit(w)
            base, dot, suffix = file.rpartition('.')
            if base != '':
                yield dot + suffix

    def resolve(self, variables, setting):
        return ' '.join(self.suffixes(data.splitwords(self._arguments[0].resolve(variables, setting))))

class BasenameFunction(Function):
    name = 'basename'
    expectedargs = 1

    @staticmethod
    def basenames(words):
        for w in words:
            dir, file = pathsplit(w, '')
            base, dot, suffix = file.rpartition('.')
            if dot == '':
                base = suffix

            yield dir + base

    def resolve(self, variables, setting):
        return ' '.join(self.basenames(data.splitwords(self._arguments[0].resolve(variables, setting))))

class AddSuffixFunction(Function):
    name = 'addprefix'
    expectedargs = 2

    def resolve(self, variables, setting):
        suffix = self._arguments[0].resolve(variables, setting)

        return ' '.join((w + suffix for w in data.splitwords(self._arguments[1].resolve(variables, setting))))

class AddPrefixFunction(Function):
    name = 'addsuffix'
    expectedargs = 2

    def resolve(self, variables, setting):
        prefix = self._arguments[0].resolve(variables, setting)

        return ' '.join((prefix + w for w in data.splitwords(self._arguments[1].resolve(variables, setting))))

class JoinFunction(Function):
    name = 'join'
    expectedargs = 2

    @staticmethod
    def iterjoin(l1, l2):
        for i in xrange(0, max(len(l1), len(l2))):
            i1 = i < len(l1) and l1[i] or ''
            i2 = i < len(l2) and l2[i] or ''
            yield i1 + i2

    def resolve(self, variables, setting):
        list1 = data.splitwords(self._arguments[0].resolve(variables, setting))
        list2 = data.splitwords(self._arguments[1].resolve(variables, setting))

        return ' '.join(self.iterjoin(list1, list2))

class WildcardFunction(Function):
    name = 'wildcard'
    expectedargs = 1

    def resolve(self, variables, setting):
        # TODO: will need work when we support -C without actually changing the OS cwd
        pattern = self._arguments[0].resolve(variables, setting)
        return ' '.join(glob.glob(pattern))

class RealpathFunction(Function):
    name = 'realpath'
    expectedargs = 1

    def resolve(self, variables, setting):
        # TODO: will need work when we support -C without actually changing the OS cwd
        return ' '.join((os.path.realpath(f)
                         for f in data.splitwords(self._arguments[0].resolve(variables, setting))))

class AbspathFunction(Function):
    name = 'abspath'
    expectedargs = 1

    def resolve(self, variables, setting):
        # TODO: will need work when we support -C without actually changing the OS cwd
        return ' '.join((os.path.abspath(f)
                         for f in data.splitwords(self._arguments[0].resolve(variables, setting))))

class IfFunction(Function):
    name = 'if'

    def setup(self):
        if len(self._arguments) < 2:
            raise DataError("Not enough arguments to function if", self.loc)
        if len(self._arguments) > 3:
            log.warning("%s: if function takes no more than three arguments, got %i" % (self.loc,))

        self._arguments[0].lstrip()
        self._arguments[0].rstrip()

    def resolve(self, variables, setting):
        condition = self._arguments[0].resolve(variables, setting)
        if len(condition):
            return self._arguments[1].resolve(variables, setting)

        if len(self._arguments) > 2:
            return self._arguments[2].resolve(variables, setting)

        return ''

class OrFunction(Function):
    name = 'or'

    def setup(self):
        pass

    def resolve(self, variables, setting):
        for arg in self._arguments:
            r = arg.resolve(variables, setting)
            if r != '':
                return r

        return ''

class AndFunction(Function):
    name = 'and'

    def setup(self):
        pass

    def resolve(self, variables, setting):
        r = ''

        for arg in self._arguments:
            r = arg.resolve(variables, setting)
            if r == '':
                return ''

        return r

class ValueFunction(Function):
    name = 'value'
    expectedargs = 1

    def resolve(self, variables, setting):
        varname = self._arguments[0].resolve(variables, setting)

        flavor, source, value = variables.get(varname, expand=False)
        return value

class FlavorFunction(Function):
    name = 'flavor'
    expectedargs = 1

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

class ShellFunction(Function):
    name = 'shell'
    expectedargs = 1

    def resolve(self, variables, setting):
        cline = self._arguments[0].resolve(variables, setting)

        p = subprocess.Popen(cline, shell=True, stdout=subprocess.PIPE)
        stdout, stderr = p.communicate()

        stdout.replace('\r\n', '\n')
        if len(stdout) > 1 and stdout[-1] == '\n':
            stdout = stdout[:-1]
        stdout.replace('\n', ' ')

        return stdout

class ErrorFunction(Function):
    name = 'error'
    expectedargs = 1

    def resolve(self, variables, setting):
        v = self._arguments[0].resolve(variables, setting)
        raise data.DataError(v, self.loc)

class WarningFunction(Function):
    name = 'warning'
    expectedargs = 1

    def resolve(self, variables, setting):
        v = self._arguments[0].resolve(variables, setting)
        log.warning(v)
        return ''

class InfoFunction(Function):
    name = 'info'
    expectedargs = 1

    def resolve(self, variables, setting):
        v = self._arguments[0].resolve(variables, setting)
        log.info(v)
        return ''

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
    'words': WordsFunction,
    'firstword': FirstWordFunction,
    'lastword': LastWordFunction,
    'dir': DirFunction,
    'notdir': NotDirFunction,
    'suffix': SuffixFunction,
    'basename': BasenameFunction,
    'addsuffix': AddSuffixFunction,
    'addprefix': AddPrefixFunction,
    'join': JoinFunction,
    'wildcard': WildcardFunction,
    'realpath': RealpathFunction,
    'abspath': AbspathFunction,
    'if': IfFunction,
    'or': OrFunction,
    'and': AndFunction,
    'foreach': None,
    'call': None,
    'value': ValueFunction,
    'eval': None,
    'origin': None,
    'flavor': FlavorFunction,
    'shell': ShellFunction,
    'error': ErrorFunction,
    'warning': WarningFunction,
    'info': InfoFunction,
}
