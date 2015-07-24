#!/usr/bin/env python2

import re # Timestamp
import unittest # Timestamp

# Classes
# IMMUTABLE
# TODO: support negatives
class Timestamp(object):
    def __init__(self, millisecond = 0):
        # TODO: raise if not integral
        self._millisecond = millisecond

    @staticmethod
    def fromParts(hour = 0, minute = 0, second = 0, millisecond = 0):
        return Timestamp(
                ((hour * 60 + minute) * 60 + second) * 1000 + millisecond)

    @staticmethod
    def fromStringParts(hour, minute, second, millisecond):
        return Timestamp.fromParts(int(hour), int(minute), int(second),
                int(millisecond.ljust(3,'0')))

    @staticmethod
    def fromString(timestamp):
        match = Timestamp.pattern_.match(timestamp)
        if match:
            return Timestamp.fromStringParts(**match.groupdict('0'))
        return None

    def components(self):
        value, millisecond = divmod(self._millisecond, 1000)
        value, second  = divmod(value, 60)
        value, minute = divmod(value, 60)
        # leftover value is hours
        return (value, minute, second, millisecond)

    def __str__(self):
        # leftover value is hours
        return ("%02d:%02d:%02d.%03d") % self.components()

    def milliseconds(self):
        return self._millisecond

    # integer operations
    def __add__(self, other):
        try:
            return Timestamp(self.milliseconds() + other.milliseconds())
        except:
            return Timestamp(self.milliseconds() + int(other))
    def __radd__(self, other):
        return self.__add__(other)

    def __mul__(self, other):
        return Timestamp(self.milliseconds() * int(other))
    def __rmul__(self, other):
        return self.__mul__(other)

    # TODO: neg, pos, abs, sub, floordiv, mod, divmod, div, truediv
    # DONTDO: pow, lshift, rshift, and, xor, or, invert


Timestamp.pattern_ = re.compile('^'
        r'(?:(?:(?P<hour>\d+):)?(?P<minute>\d+):)?' # [[hour:]minute:]
        r'(?P<second>\d+)(?:\.(?P<millisecond>\d+))?' # second[.millisecond]
        '$')


# Unit Tests
class TimestampUnitTest(unittest.TestCase):
    def testFromString(self):
        self.assertEqual(Timestamp.fromString(''), None)
        self.assertEqual(str(Timestamp.fromString('3')), '00:00:03.000')
        self.assertEqual(str(Timestamp.fromString('3.4')), '00:00:03.400')
        self.assertEqual(str(Timestamp.fromString('2:3')), '00:02:03.000')
        self.assertEqual(str(Timestamp.fromString('2:3.4')), '00:02:03.400')
        self.assertEqual(str(Timestamp.fromString('1:2:3')), '01:02:03.000')
        self.assertEqual(str(Timestamp.fromString('1:2:3.4')), '01:02:03.400')
        self.assertEqual(str(Timestamp.fromString('1:2:3.400')), '01:02:03.400')
        self.assertEqual(str(Timestamp.fromString('1:2:3.004')), '01:02:03.004')

    def testOperators(self):
        value = Timestamp.fromString('1:2:3.4')
        doubleValue = value + value
        self.assertEqual(str(doubleValue), '02:04:06.800')
        self.assertEqual(str(value + 1234), '01:02:04.634')
        self.assertEqual(str(2 * value), str(doubleValue))
        with self.assertRaises(TypeError):
            Timestamp(2) * value # multiplying times makes no sense

if __name__ == '__main__':
    unittest.main()

