import sys, imp
from util import MakeError

def call(module, method, args, env, cwd, loc):
    #XXX: keep a separate path to load modules from?
    # we could just munge sys.path?
    __import__(module)
    m = sys.modules[module]
    if not m:
        raise MakeError("No module named '%s'" % module, loc)
    if not method in m.__dict__:
        raise MakeError("No method named '%s' in module %s" % (method, module), loc)
    m.__dict__[method](args, env, cwd)

