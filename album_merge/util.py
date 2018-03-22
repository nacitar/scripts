#!/usr/bin/env python3

import os
import sys
import subprocess

import util
import timestamp

# reads lines from a file, and if the file is opened in binary mode, decodes
# those lines using the provided encoding or the system default encoding if
# none is provided.  Yields strings of the lines.
# If terminate is True, a final 'None' entry is yielded.
def line_reader(handle, terminate = False, encoding = None):
    if not encoding:
        encoding = sys.getdefaultencoding()
    while True:
        line = handle.readline().decode(encoding)
        if hasattr(line, 'decode'):
            line = line.decode(encoding)
        if not line:
            if terminate:
                yield None
            break
        yield line

def block_reader(handle, terminate = False):
    while True:
        block = input_file.read(4096)
        if not block:
            if terminate:
                yield None
            break
        yield block


def read_file(filename):
    with open(filename, 'rb') as handle:
        data = bytearray()
        for block in block_reader(handle):
            data += block
    return data

def write_file(filename, data):
    with open(filename, 'wb') as output_file:
        output_file.write(data)

def sox_info(filename):
    # sox has a bug where --info won't let you specify type, so you can't
    # have it read from stdin
    info = {}
    child = subprocess.Popen(['sox', '--info', filename],
        stdout = subprocess.PIPE)
    for line in line_reader(child.stdout):
        colon = line.find(':')
        if colon != -1:
            key = line[:colon].strip()
            value = line[colon+1:].strip()
            if value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            if key == 'Channels' or key == 'Sample Rate':
                info[key] = int(value)
            elif key == 'Duration':
                split_value = value.split(' = ')
                for part in split_value:
                    split_part = part.split(' ', 1)
                    if len(split_part) == 1:
                        info['Duration'] = timestamp.Timestamp(split_part[0])
                    elif len(split_part) == 2:
                        if split_part[1] == 'samples':
                            info['Total Samples'] = int(split_part[0])
                        elif split_part[1] == 'CDDA sectors':
                            info['CDDA Sectors'] = float(split_part[0])
            elif key == 'Precision':
                info['Bit Precision'] = int(value.split('-', 1)[0])
            elif key == 'Bit Rate':
                split_value = value.split('k', 1)
                if len(split_value) != 2 or split_value[1] != '':
                    raise RuntimeError(
                            'Unknown format for "Bit Rate": {}'.format(value))
                info[key] = int(split_value[0])
            elif key != 'Input File' and key != 'File Size':
                info[key] = value;
            elif key == 'Comments':
                break;  # not handling tags here
    child.wait()
    return info;
