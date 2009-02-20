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
