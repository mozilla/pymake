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

class _LRUItem(object):
    __slots__ = ('key', 'o', 'next', 'prev')

    def __init__(self, o, key, before):
        self.o = o
        self.key = key
        if before is None:
            self.prev = self
            self.next = self
        else:
            self.next = before
            self.prev = before.prev
            before.prev = self
            self.prev.next = self

    def movebefore(self, item):
        if self is item:
            return

        self.drop()
        self.next = item
        self.prev = item.prev
        item.prev = self
        self.prev.next = self

    def drop(self):
        self.prev.next = self.next
        self.next.prev = self.prev
        del self.next
        del self.prev

class LRUCache(object):
    def __init__(self, capacity, creationfunc, verifyfunc):
        self.capacity = capacity
        self.cfunc = creationfunc
        self.vfunc = verifyfunc

        self.count = 0
        self.d = {}
        self.head = None

    def get(self, key):
        item = self.d.get(key, None)
        if item is not None:
            item.movebefore(self.head)
            self.head = item
            if not self.vfunc(key, item.o):
                item.o = self.cfunc(key)
            return item.o

        o = self.cfunc(key)
        item = _LRUItem(o, key, self.head)
        self.head = item
        self.d[key] = item

        if self.count == self.capacity:
            tail = self.head.prev
            assert self.d[tail.key] == tail
            del self.d[tail.key]

            tail.drop()
        else:
            self.count += 1

        return o

    def debugitems(self):
        if self.head is None:
            return

        item = self.head
        tail = self.head.prev
        while True:
            yield item.key
            if item is tail:
                return
            item = item.next
