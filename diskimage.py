#!/usr/bin/python

from pynx import *
import os
import string

class LOSetup(object):
  @staticmethod
  def unused_loop():
    return ExecuteCommand(['losetup','-f'],True).output().strip()

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
  def get_mapped_devices(filename):
    output=ExecuteCommand(['losetup', '-j', filename],True).output()
    lines=output.splitlines()
    devs=[]
    for line in lines:
      devs.append(line.split(':')[0])
    return devs

  @staticmethod
  def umount_mapped_devices(filename):
    for dev in LOSetup.get_mapped_devices(filename):
      LOSetup.umount(dev)


class GDisk(object):
  @staticmethod
  def get_partitions(device_name):
    output=ExecuteCommand(['gdisk','-l',device_name],True).output()
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
  def get_link(filename):
    return ExecuteCommand(['readlink','-f',filename],True).output().strip()

  @staticmethod
  def umount_all():
    for filename in os.listdir(DiskImage.DEV_DIR):
      DiskImage.umount(filename)

  @staticmethod
  def umount(device,parts_only=False):
    device_dir=os.path.dirname(device)
    device_basename=os.path.basename(device)
    for filename in os.listdir(device_dir):
      if filename.startswith(device_basename):
        if parts_only and filename == device_basename:
          continue # skip device itself
        device_name=os.path.join(device_dir,filename)
        system_device=DiskImage.get_link(device_name)
        LOSetup.umount(system_device)
        ExecuteCommand(['unlink', device_name]).returnCode()

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
    part_list=GDisk.get_partitions(device)
    DiskImage.umount(device,parts_only=True)
    for part in part_list.parts:
      start_offset=part_list.sector_size * part.start_sector
      end_offset=part_list.sector_size * part.end_sector

      system_device=LOSetup.unused_loop()

      if LOSetup.mount(
          device,
          system_device,
          offset=start_offset,
          size=end_offset-start_offset):
        part_dev=device+str(part.number)
        if not DiskImage.makedev(system_device,part_dev):
          print "Failed to link partition " + part_dev
        else:
          print "Added partition: " + part_dev
  @staticmethod
  def mount(filename):
    system_device=LOSetup.unused_loop()
    if LOSetup.mount(filename,system_device):
      dev=DiskImage.unused_device()
      if (DiskImage.makedev(system_device,dev)):
        # TODO: no basename
        DiskImage.scan_partitions(dev)
        return dev
      LOSetup.umount(system_device)
    return None

