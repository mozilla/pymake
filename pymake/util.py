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

class SplittingIO(list):
    __slots__ = ('curword',)

    def __init__(self):
        self.curword = None

    def write(self, s):
        if not len(s):
            return

        initws = s[0].isspace()
        trailws = s[-1].isspace()

        words = s.split()
        if self.curword is not None:
            if initws:
                self.append(self.curword)
            else:
                words[0] = self.curword + words[0]

        if trailws:
            self.curword = None
        else:
            self.curword = words.pop()

        self.extend(words)

    def finish(self):
        if self.curword is not None:
            self.append(self.curword)

def joiniter(fd, it):
    """
    Given an iterator that returns strings, write the words with a space in between each.
    """
    
    it = iter(it)
    for i in it:
        fd.write(i)
        break

    for i in it:
        fd.write(' ')
        fd.write(i)

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
    from __builtin__ import any
except ImportError:
    def any(it):
        for i in it:
            if i:
                return True
        return False
