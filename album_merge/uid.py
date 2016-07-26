#!/usr/bin/env python3

import uuid
import random

def generate():
    # note: in c++ shifting by 0 is UB
    # clear out [0,64] low bits, then grab 64 bits, effectively getting
    # a random 64-bit section of the 128-bit uuid.
    return (uuid.uuid4().int >> random.randint(0, 64)) & ((1 << 64) - 1)


class Group(object):
    def __init__(self):
        self.clear()

    def clear(self):
        self._cache = set()

    def generate(self):
        while True:
            uid = generate()
            # ensure uniqueness
            if uid not in self._cache:
                self._cache.add(uid)
                return uid
