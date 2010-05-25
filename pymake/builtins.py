# Basic commands implemented in Python
import sys, os, os.path

__all__ = ["touch"]

def touch(args, variables, cwd):
    for f in args.split():
        fn = os.path.join(cwd, f)
        if os.path.exists(fn):
            os.utime(fn, None)
        else:
            open(fn, 'w').close()
