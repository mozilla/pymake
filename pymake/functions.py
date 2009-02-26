"""
Makefile functions.
"""

import parser
import data
import util
import subprocess, os, logging
from pymake.globrelative import glob
from cStringIO import StringIO

log = logging.getLogger('pymake.data')

class Function(object):
    """
    An object that represents a function call. This class is always subclassed
    with the following methods and attributes:

    minargs = minimum # of arguments
    maxargs = maximum # of arguments (0 means unlimited)

    def resolve(self, makefile, variables, setting)
        Calls the function
        @yields strings
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

    def resolve(self, makefile, variables, setting):
        vname = self.vname.resolvestr(makefile, variables, setting)
        if vname in setting:
            raise data.DataError("Setting variable '%s' recursively references itself." % (vname,), self.loc)

        flavor, source, value = variables.get(vname)
        if value is None:
            log.debug("%s: variable '%s' was not set" % (self.loc, vname))
            return

        for j in value.resolve(makefile, variables, setting + [vname]):
            yield j

class SubstitutionRef(Function):
    """$(VARNAME:.c=.o) and $(VARNAME:%.c=%.o)"""
    def __init__(self, loc, varname, substfrom, substto):
        self.loc = loc
        self.vname = varname
        self.substfrom = substfrom
        self.substto = substto

    def setup(self):
        assert False, "Shouldn't get here"

    def resolve(self, makefile, variables, setting):
        vname = self.vname.resolvestr(makefile, variables, setting)
        if vname in setting:
            raise data.DataError("Setting variable '%s' recursively references itself." % (vname,), self.loc)

        substfrom = self.substfrom.resolvestr(makefile, variables, setting)
        substto = self.substto.resolvestr(makefile, variables, setting)

        flavor, source, value = variables.get(vname)
        if value is None:
            log.debug("%s: variable '%s' was not set" % (self.loc, vname))
            return

        evalue = value.resolvestr(makefile, variables, setting + [vname])

        f = data.Pattern(substfrom)
        if not f.ispattern():
            f = data.Pattern('%' + substfrom)
            substto = '%' + substto

        yield " ".join((f.subst(substto, word, False)
                        for word in evalue.split()))

class SubstFunction(Function):
    name = 'subst'
    minargs = 3
    maxargs = 3

    def resolve(self, makefile, variables, setting):
        s = self._arguments[0].resolvestr(makefile, variables, setting)
        r = self._arguments[1].resolvestr(makefile, variables, setting)
        d = self._arguments[2].resolvestr(makefile, variables, setting)
        yield d.replace(s, r)

class PatSubstFunction(Function):
    name = 'patsubst'
    minargs = 3
    maxargs = 3

    def resolve(self, makefile, variables, setting):
        s = self._arguments[0].resolvestr(makefile, variables, setting)
        r = self._arguments[1].resolvestr(makefile, variables, setting)
        d = self._arguments[2].resolvestr(makefile, variables, setting)

        p = data.Pattern(s)
        yield ' '.join((p.subst(r, word, False)
                        for word in d.split()))

class StripFunction(Function):
    name = 'strip'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        yield ' '.join(self._arguments[0].resolvestr(makefile, variables, setting).split())

class FindstringFunction(Function):
    name = 'findstring'
    minargs = 2
    maxargs = 2

    def resolve(self, makefile, variables, setting):
        s = self._arguments[0].resolvestr(makefile, variables, setting)
        r = self._arguments[1].resolvestr(makefile, variables, setting)
        if r.find(s) == -1:
            return
        yield s

class FilterFunction(Function):
    name = 'filter'
    minargs = 2
    maxargs = 2

    def resolve(self, makefile, variables, setting):
        ps = self._arguments[0].resolvestr(makefile, variables, setting)
        d = self._arguments[1].resolvestr(makefile, variables, setting)
        plist = [data.Pattern(p) for p in ps.split()]
        r = []
        for w in d.split():
            if any((p.match(w) for p in plist)):
                    r.append(w)
                
        yield ' '.join(r)

class FilteroutFunction(Function):
    name = 'filter-out'
    minargs = 2
    maxargs = 2

    def resolve(self, makefile, variables, setting):
        ps = self._arguments[0].resolvestr(makefile, variables, setting)
        d = self._arguments[1].resolvestr(makefile, variables, setting)
        plist = [data.Pattern(p) for p in ps.split()]
        r = []
        for w in d.split():
            found = False
            if not any((p.match(w) for p in plist)):
                r.append(w)

        yield ' '.join(r)

class SortFunction(Function):
    name = 'sort'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        d = self._arguments[0].resolvestr(makefile, variables, setting)
        w = d.split()
        w.sort()
        yield ' '.join((w for w in data.withoutdups(w)))

class WordFunction(Function):
    name = 'word'
    minargs = 2
    maxargs = 2

    def resolve(self, makefile, variables, setting):
        n = self._arguments[0].resolvestr(makefile, variables, setting)
        # TODO: provide better error if this doesn't convert
        n = int(n)
        words = self._arguments[1].resolvestr(makefile, variables, setting).split()
        if n < 1 or n > len(words):
            return
        yield words[n - 1]

class WordlistFunction(Function):
    name = 'wordlist'
    minargs = 3
    maxargs = 3

    def resolve(self, makefile, variables, setting):
        nfrom = self._arguments[0].resolvestr(makefile, variables, setting)
        nto = self._arguments[1].resolvestr(makefile, variables, setting)
        # TODO: provide better errors if this doesn't convert
        nfrom = int(nfrom)
        nto = int(nto)

        words = self._arguments[2].resolvestr(makefile, variables, setting).split()

        if nfrom < 1:
            nfrom = 1
        if nto < 1:
            nto = 1

        yield ' '.join(words[nfrom - 1:nto])

class WordsFunction(Function):
    name = 'words'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        yield str(len(self._arguments[0].resolvestr(makefile, variables, setting).split()))

class FirstWordFunction(Function):
    name = 'firstword'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        wl = self._arguments[0].resolvestr(makefile, variables, setting).split()
        if len(wl) == 0:
            return
        yield wl[0]

class LastWordFunction(Function):
    name = 'lastword'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        wl = self._arguments[0].resolvestr(makefile, variables, setting).split()
        if len(wl) == 0:
            return
        yield wl[0]

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

    def resolve(self, makefile, variables, setting):
        yield ' '.join((pathsplit(path)[0]
                        for path in self._arguments[0].resolvestr(makefile, variables, setting).split()))

class NotDirFunction(Function):
    name = 'notdir'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        yield ' '.join((pathsplit(path)[1]
                        for path in self._arguments[0].resolvestr(makefile, variables, setting).split()))

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

    def resolve(self, makefile, variables, setting):
        yield ' '.join(self.suffixes(self._arguments[0].resolvestr(makefile, variables, setting).split()))

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

    def resolve(self, makefile, variables, setting):
        yield ' '.join(self.basenames(self._arguments[0].resolvestr(makefile, variables, setting).split()))

class AddSuffixFunction(Function):
    name = 'addprefix'
    minargs = 2
    maxargs = 2

    def resolve(self, makefile, variables, setting):
        suffix = self._arguments[0].resolvestr(makefile, variables, setting)

        yield ' '.join((w + suffix for w in self._arguments[1].resolvestr(makefile, variables, setting).split()))

class AddPrefixFunction(Function):
    name = 'addsuffix'
    minargs = 2
    maxargs = 2

    def resolve(self, makefile, variables, setting):
        prefix = self._arguments[0].resolvestr(makefile, variables, setting)

        yield ' '.join((prefix + w for w in self._arguments[1].resolvestr(makefile, variables, setting).split()))

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

    def resolve(self, makefile, variables, setting):
        list1 = self._arguments[0].resolvestr(makefile, variables, setting).split()
        list2 = self._arguments[1].resolvestr(makefile, variables, setting).split()

        yield ' '.join(self.iterjoin(list1, list2))

class WildcardFunction(Function):
    name = 'wildcard'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        patterns = self._arguments[0].resolvestr(makefile, variables, setting).split()

        r = []
        for p in patterns:
            r.extend([x.replace('\\','/') for x in glob(makefile.workdir, p)])
        yield ' '.join(r)

class RealpathFunction(Function):
    name = 'realpath'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        paths = self._arguments[0].resolvestr(makefile, variables, setting).split()
        fspaths = [os.path.join(makefile.workdir, path) for path in paths]
        realpaths = [os.path.realpath(path).replace('\\','/') for path in fspaths]
        yield ' '.join(realpaths)

class AbspathFunction(Function):
    name = 'abspath'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        assert os.path.isabs(makefile.workdir)
        paths = self._arguments[0].resolvestr(makefile, variables, setting).split()
        fspaths = [os.path.join(makefile.workdir, path).replace('\\','/') for path in paths]
        yield ' '.join(fspaths)

class IfFunction(Function):
    name = 'if'
    minargs = 1
    maxargs = 3

    def setup(self):
        Function.setup(self)
        self._arguments[0].lstrip()
        self._arguments[0].rstrip()

    def resolve(self, makefile, variables, setting):
        condition = self._arguments[0].resolvestr(makefile, variables, setting)
        if len(condition):
            for j in self._arguments[1].resolvestr(makefile, variables, setting):
                yield j
        elif len(self._arguments) > 2:
            for j in self._arguments[2].resolvestr(makefile, variables, setting):
                yield j

class OrFunction(Function):
    name = 'or'
    minargs = 1
    maxargs = 0

    def resolve(self, makefile, variables, setting):
        for arg in self._arguments:
            r = arg.resolvestr(makefile, variables, setting)
            if r != '':
                yield r
                return

class AndFunction(Function):
    name = 'and'
    minargs = 1
    maxargs = 0

    def resolve(self, makefile, variables, setting):
        r = ''

        for arg in self._arguments:
            r = arg.resolvestr(makefile, variables, setting)
            if r == '':
                return

        yield r

class ForEachFunction(Function):
    name = 'foreach'
    minargs = 3
    maxargs = 3

    def resolve(self, makefile, variables, setting):
        vname = self._arguments[0].resolvestr(makefile, variables, setting)
        words = self._arguments[1].resolvestr(makefile, variables, setting).split()

        e = self._arguments[2]

        v = data.Variables(parent=variables)
        for i in xrange(0, len(words)):
            w = words[i]
            if i > 0:
                yield ' '

            v.set(vname, data.Variables.FLAVOR_SIMPLE, data.Variables.SOURCE_AUTOMATIC, w)
            for j in e.resolve(makefile, v, setting):
                yield j

class CallFunction(Function):
    name = 'call'
    minargs = 1
    maxargs = 0

    def resolve(self, makefile, variables, setting):
        vname = self._arguments[0].resolvestr(makefile, variables, setting)
        if vname in setting:
            raise data.DataError("Recursively setting variable '%s'" % (vname,))

        v = data.Variables(parent=variables)
        v.set('0', data.Variables.FLAVOR_SIMPLE, data.Variables.SOURCE_AUTOMATIC, vname)
        for i in xrange(1, len(self._arguments)):
            param = self._arguments[i].resolvestr(makefile, variables, setting)
            v.set(str(i), data.Variables.FLAVOR_SIMPLE, data.Variables.SOURCE_AUTOMATIC, param)

        flavor, source, e = variables.get(vname)
        if e is None:
            return

        if flavor == data.Variables.FLAVOR_SIMPLE:
            log.warning("%s: calling variable '%s' which is simply-expanded" % (self.loc, vname))

        # but we'll do it anyway
        for j in e.resolve(makefile, v, setting + [vname]):
            yield j

class ValueFunction(Function):
    name = 'value'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        varname = self._arguments[0].resolvestr(makefile, variables, setting)

        flavor, source, value = variables.get(varname, expand=False)
        if value is None:
            return

        yield value

class EvalFunction(Function):
    name = 'eval'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        if makefile.parsingfinished:
            # GNU make allows variables to be set by recursive expansion during
            # command execution. This seems really dumb to me, so I don't!
            raise data.DataError("$(eval) not allowed via recursive expansion after parsing is finished", self.loc)

        text = StringIO(self._arguments[0].resolvestr(makefile, variables, setting))
        stmts = parser.parsestream(text, 'evaluation from %s' % self.loc)
        stmts.execute(makefile)
        return
        yield

class OriginFunction(Function):
    name = 'origin'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        vname = self._arguments[0].resolvestr(makefile, variables, setting)

        flavor, source, value = variables.get(vname)
        if source is None:
            yield 'undefined'
        elif source == data.Variables.SOURCE_OVERRIDE:
            yield 'override'
        elif source == data.Variables.SOURCE_MAKEFILE:
            yield 'file'
        elif source == data.Variables.SOURCE_ENVIRONMENT:
            yield 'environment'
        elif source == data.Variables.SOURCE_COMMANDLINE:
            yield 'command line'
        elif source == data.Variables.SOURCE_AUTOMATIC:
            yield 'automatic'
        else:
            assert False, "Unexpected source value: %s" % source

class FlavorFunction(Function):
    name = 'flavor'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        varname = self._arguments[0].resolvestr(makefile, variables, setting)
        
        flavor, source, value = variables.get(varname)
        if flavor is None:
            yield 'undefined'
        elif flavor == data.Variables.FLAVOR_RECURSIVE:
            yield 'recursive'
        elif flavor == data.Variables.FLAVOR_SIMPLE:
            yield 'simple'
        else:
            assert False, "Neither simple nor recursive?"

class ShellFunction(Function):
    name = 'shell'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        #TODO: call this once up-front somewhere and save the result?
        shell, msys = util.checkmsyscompat()
        cline = self._arguments[0].resolvestr(makefile, variables, setting)

        log.debug("%s: running shell command '%s'" % (self.loc, cline))
        if msys:
            cline = [shell, "-c", cline]
        p = subprocess.Popen(cline, shell=not msys, stdout=subprocess.PIPE, cwd=makefile.workdir)
        stdout, stderr = p.communicate()

        stdout = stdout.replace('\r\n', '\n')
        if len(stdout) > 1 and stdout[-1] == '\n':
            stdout = stdout[:-1]
        stdout = stdout.replace('\n', ' ')

        yield stdout

class ErrorFunction(Function):
    name = 'error'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        v = self._arguments[0].resolvestr(makefile, variables, setting)
        raise data.DataError(v, self.loc)

class WarningFunction(Function):
    name = 'warning'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        v = self._arguments[0].resolvestr(makefile, variables, setting)
        log.warning(v)
        return
        yield

class InfoFunction(Function):
    name = 'info'
    minargs = 1
    maxargs = 1

    def resolve(self, makefile, variables, setting):
        v = self._arguments[0].resolvestr(makefile, variables, setting)
        log.info(v)
        return
        yield

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
