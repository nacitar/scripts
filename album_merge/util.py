#!/usr/bin/env python3

import sys

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

