#!/usr/bin/env python3

def read_file(filename):
    with open(filename, 'rb') as input_file:
        data = bytearray()
        while True:
            block = input_file.read(4096)
            if not block:
                break
            data += block
    return data

def write_file(filename, data):
    with open(filename, 'wb') as output_file:
        output_file.write(data)
