import os

def makeobject(proplist, **kwargs):
    class P(object):
        __slots__ = proplist

    p = P()
    for k, v in kwargs.iteritems():
        setattr(p, k, v)
    return p

class MakeError(Exception):
    def __init__(self, message, loc=None):
        self.message = message
        self.loc = loc

    def __str__(self):
        locstr = ''
        if self.loc is not None:
            locstr = "%s:" % (self.loc,)

        return "%s%s" % (locstr, self.message)

def itersplit(it):
    """
    Given an iterator that returns strings, yield words as if string.split() had been called on the concatenation
    of the strings.
    """

    curword = None
    for s in it:
        if not len(s):
            continue

        initws = s[0].isspace()
        trailws = s[-1].isspace()

        words = s.split()
        if curword is not None:
            if initws:
                yield curword
            else:
                words[0] = curword + words[0]

        if trailws:
            curword = None
        else:
            curword = words.pop()

        for w in words:
            yield w

    if curword is not None:
        yield curword

def joiniter(it, j=' '):
    """
    Given an iterator that returns strings, yield the words with j inbetween each.
    """
    it = iter(it)
    for i in it:
        yield i
        break

    for i in it:
        yield j
        yield i

def checkmsyscompat():
    """For msys compatibility on windows, honor the SHELL environment variable,
    and if $MSYSTEM == MINGW32, run commands through $SHELL -c instead of
    letting Python use the system shell."""
    if 'SHELL' in os.environ:
        shell = os.environ['SHELL']
    elif 'COMSPEC' in os.environ:
        shell = os.environ['COMSPEC']
    else:
        raise DataError("Can't find a suitable shell!")

    msys = False
    if 'MSYSTEM' in os.environ and os.environ['MSYSTEM'] == 'MINGW32':
        msys = True
        if not shell.lower().endswith(".exe"):
            shell += ".exe"
    return (shell, msys)

if hasattr(str, 'partition'):
    def strpartition(str, token):
        return str.partition(token)

    def strrpartition(str, token):
        return str.rpartition(token)

else:
    def strpartition(str, token):
        """Python 2.4 compatible str.partition"""

        offset = str.find(token)
        if offset == -1:
            return str, '', ''

        return str[:offset], token, str[offset + len(token):]

    def strrpartition(str, token):
        """Python 2.4 compatible str.rpartition"""

        offset = str.rfind(token)
        if offset == -1:
            return '', '', str

        return str[:offset], token, str[offset + len(token):]

try:
    from __builtins__ import any
except ImportError:
    def any(it):
        for i in it:
            if i:
                return True
        return False
