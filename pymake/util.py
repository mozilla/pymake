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
