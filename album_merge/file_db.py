#!/usr/bin/env python3
import hashlib

class FileDB(object):
    def __init__(self):
        self._digest_map = {}

    def add(self, data):
        digest = hashlib.sha1(data).digest()
        if digest not in self._digest_map:
            self._digest_map[digest] = data
        return digest

    def clear(self):
        self._digest_map.clear()

    def get(self, digest):
        return self._digest_map[digest]

