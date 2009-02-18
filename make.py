#!/usr/bin/env python

"""
make.py

A drop-in or mostly drop-in replacement for GNU make.
"""

import pymake.command, sys, os

sys.exit(pymake.command.main(sys.argv[1:], os.environ, os.getcwd()))
