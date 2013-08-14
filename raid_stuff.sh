#!/bin/bash
quicksmart() {
  DRIVE_SELECT="$1"
  : ${DRIVE_SELECT:='/dev/msd?'}
  for DRIVE in $DRIVE_SELECT; do
    REALDRIVE=$(ls -l $DRIVE | awk '{print $11}')
    echo; echo "SMART data for $DRIVE ($REALDRIVE):"; echo
    smartctl -a $DRIVE | grep -e "self-ass"; echo
    smartctl -a $DRIVE | grep -e "Reallocated"\
                              -e "Celsius"\
                              -e "Pending"\
                              -e "RAW_VALUE"\
                              -e "Hours"\
                              -e "Uncorrectable"\
                       | awk '{print $2,$4,$5,$6,$9,$10}' | column -t; echo
    sep 75
  done
}

raidboost() {
  echo 50000 > /proc/sys/dev/raid/speed_limit_min
  blockdev --setra 65536 /dev/md0
  echo 2048 > /sys/block/md0/md/stripe_cache_size # Used 5GB of RAM
  mdadm --grow --bitmap=internal /dev/md0
}

raidunboost() {
  echo 1000 > /proc/sys/dev/raid/speed_limit_min
  blockdev --setra 1024 /dev/md0
  echo 256 > /sys/block/md0/md/stripe_cache_size
  mdadm --grow --bitmap=none /dev/md0
}

raidstatus() {
  for RAID in /dev/md*; do
    DEVICE_COUNT=$(mdadm -D /dev/md0 | grep "Raid Devices" | awk '{print $4}')
    echo; echo "Raid: $RAID"
    mdadm -D $RAID | grep -e "Devices" -e "State :" -e "Raid Level"
    echo; echo "RAID Devices:"
    mdadm -D $RAID | tail -n $DEVICE_COUNT | column -t
    echo; echo "Device Mappings:"
    getmaps
    echo; echo "mdstat:"
    cat /proc/mdstat
    echo
  done
}
