#!/usr/bin/python


from diskimage import *
import sys

if __name__ == '__main__':
  if len(sys.argv) < 2:
    print "Give me some image files!"
    sys.exit(1)

  for filename in sys.argv[1:]:
    DiskImage.mount(filename)
