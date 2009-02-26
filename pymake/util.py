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
