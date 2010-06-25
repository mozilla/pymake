def writetofile(args, variables):
  with open(args[0], 'w') as f:
    f.write(' '.join(args[1:]))
