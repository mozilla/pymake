#!/usr/bin/env python

"""
make.py

A drop-in or mostly drop-in replacement for GNU make.
"""

import sys, os
import pymake.command, pymake.process

import gc

if __name__ == '__main__':
  if sys.version_info < (3,0):
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
    sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', 0)
  else:
    # Unbuffered text I/O is not allowed in Python 3.
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w')
    sys.stderr = os.fdopen(sys.stderr.fileno(), 'w')

  gc.disable()

  pymake.command.main(sys.argv[1:], os.environ, os.getcwd(), cb=sys.exit)
  pymake.process.ParallelContext.spin()
  assert False, "Not reached"
