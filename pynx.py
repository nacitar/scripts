#!/usr/bin/python

import os
import sys
import subprocess
import urllib

# backwards compatible is_string
IS_PY2 = sys.version_info[0] == 2
if IS_PY2:
    def is_string(obj):
        return isinstance(obj, basestring)
else:
    def is_string(obj):
        return isinstance(obj, str)

def is_integral(obj):
  return isinstance(obj,int) or isinstance(obj,long)

def listize(obj):
  if isinstance(obj,tuple) or isinstance(obj,list):
    return list(obj)
  return [obj]

def dictize(obj):
  if not isinstance(obj,dict):
    obj=listize(obj)
    obj=dict(zip(xrange(len(obj)), obj)) # convert lists into index-keyed dicts
  return obj

#
# Supplemental language features
#
def enum(*sequential, **named):
  """ Creates a sequentially numbered enum given string arguments.  Specifying keyword
  arguments and assigning an explicit value will also work. Additionally, adds a member
  dictionary "inverse_map" that contains the inverse mapping.  However, because a dictionary
  is potentially N keys to 1 value, the inverse mapping provides a list of keys.  Even
  if a value only inversely maps to a single key, that key will be provided in a single
  element list comprehension.
  """
  enums = dict(zip(sequential, range(len(sequential))), **named)
  # get the reverse mapping
  inv_map = {}
  for k, v in enums.iteritems():
    inv_map[v] = inv_map.get(v, [])
    inv_map[v].append(k)
  enums["inverse_map"] = inv_map
  return type('Enum', (), enums)

class keyword_object(object):
  """ Simple class that accepts named arguments and sets attributes for each of them. """
  def __init__(self, **entries):
    self._obj_keys = entries.keys()
    self.__dict__.update(entries)

  def __str__(self):
    result=""
    for key in self._obj_keys:
      if result:
        result += os.linesep
      result += str(key) + ": " + str(getattr(self,key))
    return result

#
# Enums
#
Platform = enum('WIN','MAC','LINUX')

def get_platform():
  """ Returns the current platform. """
  platform_str=sys.platform
  if platform_str.startswith("win"):
    return Platform.WIN
  elif platform_str.startswith("darwin"):
    return Platform.MAC
  # assuming linux
  return Platform.LINUX


class ExecutingCommand(object):
  def __init__(self,cmd_arg_list,get_output=False,wait=True):
    # Allow strings to be passed for no-arg commands
    self.cmd_arg_list=listize(cmd_arg_list)
    self.get_output=get_output

    if self.get_output:
      stdout=subprocess.PIPE
      stderr=subprocess.PIPE
    else:
      stdout=None
      stderr=None

    platform=get_platform()
    # close fds on non-windows
    close_fds=(platform != Platform.WIN)

    # TODO: fix this mac hack?
    if platform == Platform.MAC:
      if cmd_arg_list and cmd_arg_list[0].endswith('.app'):
        new_arg_list = [ '/usr/bin/open', '-W' ]
        new_arg_list.extend(cmd_arg_list)
        cmd_arg_list = new_arg_list

    # for debugging
    print "EXECUTECOMMAND: " + repr(cmd_arg_list)
    self.child=subprocess.Popen(
        cmd_arg_list,
        close_fds=close_fds,
        stdout=stdout,
        stderr=stderr)
    if wait:
      self.wait()

  def wait(self):
    self.child.wait()

  def output(self):
    """ Returns a tuple of the program's stdout and stderr output, if it was
    captured.  Can be called only once, and retrieves the entire output of the
    program. """
    return self.child.communicate()

  def returnCode(self):
    return self.child.returncode

def ExecuteCommand(arg_list,get_output=False):
  """ Executes the provided command/argument list and returns either the returncode if get_output=False, or a tuple of the returncode
  and the program output as a list if get_output=True

  Keyword arguments:
    arg_list -- a list with the first element being the command name and the rest being arguments to that command
    get_output -- whether or not we want to capture the program output (default False)
  """
  return ExecutingCommand(arg_list,get_output=get_output)

def get_shared_deps(binary_filepath):
  cmd_arg_list=listize(binary_filepath)
  platform=get_platform()
  if platform == Platform.LINUX:
    cmd_arg_list=[ 'ldd' ]
  elif platform == Platform.MAC:
    cmd_arg_list=[ 'otool', '-XL' ]
  else:
    raise Exception('UNIMPLEMENTED: Cannot get shared deps on this platform.')
  cmd_arg_list.append(binary_filepath)

  child=ExecuteCommand(cmd_arg_list,get_output=True)
  child.wait()
  output=child.output()
  result=[]
  for line in output.splitlines():

    # remove last token if present, for each of the delimiters
    for delim in [ ' (', ' => ' ]:
      parts=line.split(delim)
      if len(parts) > 1:
        line=delim.join(parts[0:-1])
    result.append(line.strip())
  return result


def wget(url,destfile):
  """ Attempts to download a file, raising an exception if it fails. """
  urllib.urlretrieve(str(url),str(destfile))
