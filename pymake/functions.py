"""
Makefile functions.
"""

from pymake import data
import subprocess, os, glob

log = data.log

class Function(object):
    """
    An object that represents a function call. This class is always subclassed
    with the following methods and attributes:

    minargs = minimum # of arguments
    maxargs = maximum # of arguments (0 means unlimited)

    def resolve(self, variables, setting)
        Calls the function
        @returns string
    """
    def __init__(self, loc):
        self._arguments = []
        self.loc = loc
        assert self.minargs > 0

    def __getitem__(self, key):
        return self._arguments[key]

    def setup(self):
        argc = len(self._arguments)

        if argc < self.minargs:
            raise data.DataError("Not enough arguments to function %s, requires %s" % (self.name, self.minargs), self.loc)

        assert self.maxargs == 0 or argc <= self.maxargs, "Parser screwed up, gave us too many args"

    def append(self, arg):
        assert isinstance(arg, data.Expansion)
        self._arguments.append(arg)

    def __len__(self):
        return len(self._arguments)

class VariableRef(Function):
    def __init__(self, loc, vname):
        self.loc = loc
        assert isinstance(vname, data.Expansion)
        self.vname = vname
        
    def setup(self):
        assert False, "Shouldn't get here"

    def resolve(self, variables, setting):
        vname = self.vname.resolve(variables, setting)
        if vname in setting:
            raise data.DataError("Setting variable '%s' recursively references itself." % (vname,), self.loc)

        flavor, source, value = variables.get(vname)
        if value is None:
            log.debug("%s: variable '%s' was not set" % (self.loc, vname))
            return ''

        return value.resolve(variables, setting + [vname])

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
        if vname in setting:
            raise data.DataError("Setting variable '%s' recursively references itself." % (vname,), self.loc)

        substfrom = self.substfrom.resolve(variables, setting)
        substto = self.substto.resolve(variables, setting)

        flavor, source, value = variables.get(vname)
        if value is None:
            log.debug("%s: variable '%s' was not set" % (self.loc, vname))
            return ''

        evalue = value.resolve(variables, setting + [vname])
        words = data.splitwords(evalue)

        f = data.Pattern(substfrom)
        if not f.ispattern():
            f = data.Pattern('%' + substfrom)
            substto = '%' + substto

        return " ".join((f.subst(substto, word, False)
                         for word in words))

class SubstFunction(Function):
    name = 'subst'
    minargs = 3
    maxargs = 3

    def resolve(self, variables, setting):
        s = self._arguments[0].resolve(variables, setting)
        r = self._arguments[1].resolve(variables, setting)
        d = self._arguments[2].resolve(variables, setting)
        return d.replace(s, r)

class PatSubstFunction(Function):
    name = 'patsubst'
    minargs = 3
    maxargs = 3

    def resolve(self, variables, setting):
        s = self._arguments[0].resolve(variables, setting)
        r = self._arguments[1].resolve(variables, setting)
        d = self._arguments[2].resolve(variables, setting)

        p = data.Pattern(s)
        return ' '.join((p.subst(r, word, False)
                         for word in data.splitwords(d)))

class StripFunction(Function):
    name = 'strip'
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        return ' '.join(data.splitwords(self._arguments[0].resolve(variables, setting)))

class FindstringFunction(Function):
    name = 'findstring'
    minargs = 2
    maxargs = 2

    def resolve(self, variables, setting):
        s = self._arguments[0].resolve(variables, setting)
        r = self._arguments[1].resolve(variables, setting)
        if r.find(s) == -1:
            return ''
        return s

class FilterFunction(Function):
    name = 'filter'
    minargs = 2
    maxargs = 2

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
    minargs = 2
    maxargs = 2

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
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        d = self._arguments[0].resolve(variables, setting)
        w = data.splitwords(d)
        w.sort()
        return ' '.join((w for w in data.withoutdups(w)))

class WordFunction(Function):
    name = 'word'
    minargs = 2
    maxargs = 2

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
    minargs = 3
    maxargs = 3

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
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        return str(len(data.splitwords(self._arguments[0].resolve(variables, setting))))

class FirstWordFunction(Function):
    name = 'firstword'
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        wl = data.splitwords(self._arguments[0].resolve(variables, setting))
        if len(wl) == 0:
            return ''
        return wl[0]

class LastWordFunction(Function):
    name = 'lastword'
    minargs = 1
    maxargs = 1

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
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        return ' '.join((pathsplit(path)[0]
                         for path in data.splitwords(self._arguments[0].resolve(variables, setting))))

class NotDirFunction(Function):
    name = 'notdir'
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        return ' '.join((pathsplit(path)[1]
                         for path in data.splitwords(self._arguments[0].resolve(variables, setting))))

class SuffixFunction(Function):
    name = 'suffix'
    minargs = 1
    maxargs = 1

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
    minargs = 1
    maxargs = 1

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
    minargs = 2
    maxargs = 2

    def resolve(self, variables, setting):
        suffix = self._arguments[0].resolve(variables, setting)

        return ' '.join((w + suffix for w in data.splitwords(self._arguments[1].resolve(variables, setting))))

class AddPrefixFunction(Function):
    name = 'addsuffix'
    minargs = 2
    maxargs = 2

    def resolve(self, variables, setting):
        prefix = self._arguments[0].resolve(variables, setting)

        return ' '.join((prefix + w for w in data.splitwords(self._arguments[1].resolve(variables, setting))))

class JoinFunction(Function):
    name = 'join'
    minargs = 2
    maxargs = 2

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
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        # TODO: will need work when we support -C without actually changing the OS cwd
        pattern = self._arguments[0].resolve(variables, setting)
        return ' '.join(glob.glob(pattern))

class RealpathFunction(Function):
    name = 'realpath'
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        # TODO: will need work when we support -C without actually changing the OS cwd
        return ' '.join((os.path.realpath(f)
                         for f in data.splitwords(self._arguments[0].resolve(variables, setting))))

class AbspathFunction(Function):
    name = 'abspath'
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        # TODO: will need work when we support -C without actually changing the OS cwd
        return ' '.join((os.path.abspath(f)
                         for f in data.splitwords(self._arguments[0].resolve(variables, setting))))

class IfFunction(Function):
    name = 'if'
    minargs = 1
    maxargs = 3

    def setup(self):
        Function.setup(self)
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
    minargs = 1
    maxargs = 0

    def resolve(self, variables, setting):
        for arg in self._arguments:
            r = arg.resolve(variables, setting)
            if r != '':
                return r

        return ''

class AndFunction(Function):
    name = 'and'
    minargs = 1
    maxargs = 0

    def resolve(self, variables, setting):
        r = ''

        for arg in self._arguments:
            r = arg.resolve(variables, setting)
            if r == '':
                return ''

        return r

class ForEachFunction(Function):
    name = 'foreach'
    minargs = 3
    maxargs = 3

    def resolve(self, variables, setting):
        vname = self._arguments[0].resolve(variables, setting)

        words = data.splitwords(self._arguments[1].resolve(variables, setting))
        e = self._arguments[2]

        results = []

        v = data.Variables(parent=variables)
        for w in words:
            v.set(vname, data.Variables.FLAVOR_SIMPLE, data.Variables.SOURCE_AUTOMATIC, w)
            results.append(e.resolve(v, setting))

        return ' '.join(results)

class CallFunction(Function):
    name = 'call'
    minargs = 1
    maxargs = 0

    def resolve(self, variables, setting):
        vname = self._arguments[0].resolve(variables, setting)
        if vname in setting:
            raise data.DataError("Recursively setting variable '%s'" % (vname,))

        v = data.Variables(parent=variables)
        v.set('0', data.Variables.FLAVOR_SIMPLE, data.Variables.SOURCE_AUTOMATIC, vname)
        for i in xrange(1, len(self._arguments)):
            param = self._arguments[i].resolve(variables, setting)
            v.set(str(i), data.Variables.FLAVOR_SIMPLE, data.Variables.SOURCE_AUTOMATIC, param)

        flavor, source, e = variables.get(vname)
        if e is None:
            return ''

        if flavor == data.Variables.FLAVOR_SIMPLE:
            log.warning("%s: calling variable '%s' which is simply-expanded" % (self.loc, vname))

        # but we'll do it anyway
        return e.resolve(v, setting + [vname])

class ValueFunction(Function):
    name = 'value'
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        varname = self._arguments[0].resolve(variables, setting)

        flavor, source, value = variables.get(varname, expand=False)
        if value is None:
            return ''

        return value

class EvalFunction(Function):
    name = 'eval'
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        raise NotImplementedError('no eval yet')

class OriginFunction(Function):
    name = 'origin'
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        vname = self._arguments[0].resolve(variables, setting)

        flavor, source, value = variables.get(vname)
        if source is None:
            return 'undefined'

        if source == data.Variables.SOURCE_OVERRIDE:
            return 'override'

        if source == data.Variables.SOURCE_MAKEFILE:
            return 'file'

        if source == data.Variables.SOURCE_ENVIRONMENT:
            return 'environment'

        if source == data.Variables.SOURCE_COMMANDLINE:
            return 'command line'

        if source == data.Variables.SOURCE_AUTOMATIC:
            return 'automatic'

        assert False, "Unexpected source value: %s" % source

class FlavorFunction(Function):
    name = 'flavor'
    minargs = 1
    maxargs = 1

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
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        cline = self._arguments[0].resolve(variables, setting)

        p = subprocess.Popen(cline, shell=True, stdout=subprocess.PIPE)
        stdout, stderr = p.communicate()

        stdout = stdout.replace('\r\n', '\n')
        if len(stdout) > 1 and stdout[-1] == '\n':
            stdout = stdout[:-1]
        stdout = stdout.replace('\n', ' ')

        return stdout

class ErrorFunction(Function):
    name = 'error'
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        v = self._arguments[0].resolve(variables, setting)
        raise data.DataError(v, self.loc)

class WarningFunction(Function):
    name = 'warning'
    minargs = 1
    maxargs = 1

    def resolve(self, variables, setting):
        v = self._arguments[0].resolve(variables, setting)
        log.warning(v)
        return ''

class InfoFunction(Function):
    name = 'info'
    minargs = 1
    maxargs = 1

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
    'foreach': ForEachFunction,
    'call': CallFunction,
    'value': ValueFunction,
    'eval': EvalFunction,
    'origin': OriginFunction,
    'flavor': FlavorFunction,
    'shell': ShellFunction,
    'error': ErrorFunction,
    'warning': WarningFunction,
    'info': InfoFunction,
}
