#!/usr/bin/env python

"""
make.py

A drop-in or mostly drop-in replacement for GNU make.
"""

import sys, os
import pymake.command

pymake.command.main(sys.argv[1:], os.environ, os.getcwd(), context=None, cb=sys.exit)

raise Exception("Not reached")
