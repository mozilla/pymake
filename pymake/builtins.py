# Basic commands implemented in Python
import sys, os, os.path, time

__all__ = ["touch", "sleep"]

def touch(args, variables, cwd):
    for f in args:
        fn = os.path.join(cwd, f)
        if os.path.exists(fn):
            os.utime(fn, None)
        else:
            open(fn, 'w').close()

def sleep(args, variables, cwd):
    time.sleep(int(args[0]))
