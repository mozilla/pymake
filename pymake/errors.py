

class MakeError(Exception):
    def __init__(self, message, loc=None):
        self.msg = message
        self.loc = loc

    def __str__(self):
        locstr = ''
        if self.loc is not None:
            locstr = "%s:" % (self.loc,)

        return "%s%s" % (locstr, self.msg)


class SyntaxError(MakeError):
    pass


class DataError(MakeError):
    pass


class ResolutionError(DataError):
    """
    Raised when dependency resolution fails, either due to recursion or to missing
    prerequisites.This is separately catchable so that implicit rule search can try things
    without having to commit.
    """
    pass


class PythonError(Exception):
    def __init__(self, message, exitcode):
        Exception.__init__(self)
        self.message = message
        self.exitcode = exitcode

    def __str__(self):
        return self.message


