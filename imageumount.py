#!/usr/bin/python


from diskimage import *
import sys

if __name__ == '__main__':
  if len(sys.argv) < 2:
    print "Give me some device names!"
    sys.exit(1)
  for device in sys.argv[1:]:
    DiskImage.umount(device)
