#!/usr/bin/python

from pynx import *
import os
import string

class LinuxCommand(object):
  @staticmethod
  def realpath(filename):
    return ExecuteCommand(['readlink','-f',filename],True).output()[0].strip()

  @staticmethod
  def unlink(filename):
    return ExecuteCommand(['unlink', filename]).returnCode()

class LOSetup(object):
  @staticmethod
  def unused_loop():
    return ExecuteCommand(['losetup','-f'],True).output()[0].strip()

  @staticmethod
  def umount(device):
    return ExecuteCommand(['losetup', '-d', device]).returnCode()

  @staticmethod
  def umount_all():
    return ExecuteCommand(['losetup', '-D']).returnCode()

  @staticmethod
  def mount(filename,device,offset=None,size=None):
    cmd=[ 'losetup' ]

    if offset is not None:
      cmd.extend(['--offset',str(offset)])
    if size is not None:
      cmd.extend(['--sizelimit',str(size)])

    cmd.extend([device,filename])
    return (ExecuteCommand(cmd).returnCode() == 0)

  @staticmethod
  def process_line(line):
    # /dev/loop0: [2051]:811924 (/path/to/img)
    start_file=line.find('(')
    end_file=line.rfind(')')
    end_device=line.find(':')

    if start_file != -1 and end_file != -1:
      image=LinuxCommand.realpath(line[start_file+1:end_file])
    else:
      image=None

    if end_device != -1:
      device=LinuxCommand.realpath(line[0:end_device])
    else:
      device=None

    if image or device:
      return keyword_object(device=device,image=image)
    return None


  @staticmethod
  def get_mappings(dev_or_file):
    dev_or_file=LinuxCommand.realpath(dev_or_file)
    lines=ExecuteCommand(
        ['losetup', dev_or_file],True).output()[0].strip().splitlines()
    lines.extend(ExecuteCommand(
        ['losetup', '-j', dev_or_file],True).output()[0].strip().splitlines())
    mappings=[]
    for line in lines:
      item = LOSetup.process_line(line)
      if item:
        mappings.append(item)
    return mappings

  @staticmethod
  def umount_mapped_devices(file_or_dev):
    for item in LOSetup.get_mappings(file_or_dev):
      LOSetup.umount(item.device)


class GDisk(object):
  @staticmethod
  def get_partitions(device_name):
    output=ExecuteCommand(['gdisk','-l',device_name],True).output()[0]
    lines=output.splitlines()
    parts=[]

    sector_size=None
    got_headers=False
    for line in lines:
      if not got_headers:
        if line.startswith("Number"):
          got_headers=True
          continue
        if not sector_size and line.startswith("Logical sector size:"):
          sector_size=int(line[line.find(':')+2:].split(' ')[0])
      else:
        # got headers
        values=line.split()
        parts.append(
            keyword_object(
                number=int(values[0]),
                start_sector=int(values[1]),
                end_sector=int(values[2]),
                code=int(values[5])))
    return keyword_object(sector_size=sector_size,parts=parts)


class DiskImage(object):
  DEV_DIR=os.path.join(os.environ['HOME'],'lodev')

  @staticmethod
  def get_devices(mappings):
    devs=[]
    for filename in os.listdir(DiskImage.DEV_DIR):
      filename = os.path.join(DiskImage.DEV_DIR,filename)
      rp=LinuxCommand.realpath(filename)
      for item in mappings:
        if rp == item.device:
          devs.append(filename)
    return devs

  @staticmethod
  def umount_all():
    for filename in os.listdir(DiskImage.DEV_DIR):
      DiskImage.umount(filename)

  @staticmethod
  def umount(device,parts_only=False):
    mappings=LOSetup.get_mappings(device)
    devs=DiskImage.get_devices(mappings)
    for item in mappings:
      LOSetup.umount(item.device)
    for dev in devs:
      LinuxCommand.unlink(dev)

  @staticmethod
  def unused_device():
    for ch in string.ascii_lowercase:
      devname=os.path.join(DiskImage.DEV_DIR,'td'+ch)
      if not os.path.exists(devname):
        return devname
    return None

  @staticmethod
  def makedev(system_device, device):
    return (ExecuteCommand(
        ['ln', '-sf', system_device, device]).returnCode()==0)

  @staticmethod
  def scan_partitions(device):
    image=LOSetup.get_mappings(device)[0].image
    for filename in os.listdir(DiskImage.DEV_DIR):
      if filename.startswith(image) and filename != image:
        LinuxCommand.unlink(os.path.join(DiskImage.DEV_DIR,filename))

    part_list=GDisk.get_partitions(image)
    for part in part_list.parts:
      start_offset=part_list.sector_size * part.start_sector
      end_offset=part_list.sector_size * part.end_sector

      system_device=LOSetup.unused_loop()

      if LOSetup.mount(
          image,
          system_device,
          offset=start_offset,
          size=end_offset-start_offset):
        part_dev=device+str(part.number)
        DiskImage.makedev(system_device,part_dev)
  @staticmethod
  def mount(filename):
    system_device=LOSetup.unused_loop()
    if LOSetup.mount(filename,system_device):
      dev=DiskImage.unused_device()
      if (DiskImage.makedev(system_device,dev)):
        DiskImage.scan_partitions(dev)
        return dev
      return dev
    return None

