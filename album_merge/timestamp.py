#!/usr/bin/env python3

import unit

class Timestamp(object):
    _UNITS = [unit.HR, unit.MIN, unit.SEC, unit.NS]

    def __init__(self, value=0):
        if isinstance(value, str):
            # if a timestamp is provided that's outside of range, like 65
            # minutes for example, 65 minutes are in fact added to the offset,
            # so converting back to string won't result in an identical
            # timestamp, but rather a valid one will be produced.
            self.nanoseconds = 0
            parts = value.split(':')
            if len(parts) > 3:
                raise ValueError('Timestamp string has too many ":"'
                        ' components.')
            # start at the correct unit
            unit_iter = iter(Timestamp._UNITS[3 - len(parts):])
            for part in parts:
                cur_unit = next(unit_iter)
                if cur_unit == unit.SEC:
                    extra = part.split('.')
                    if len(extra) > 2:
                        raise ValueError('Timestamp string has too many "."'
                                ' second components.')
                    part = extra.pop(0) # remove the seconds
                    parts.extend(extra) # append nanoseconds (or nothing)
                elif cur_unit == unit.NS:
                    if part: # leave blank if empty, so int() fails below
                        if len(part) > 9:
                            raise ValueError('Timestamp has only nanosecond'
                                    ' precision.')
                        # pad to the right, truncating the value to at
                        # most 9 digits
                        part = '{:0<9.9}'.format(part)
                # add this part
                self.nanoseconds += int(part) * cur_unit
        else:
            self.nanoseconds = int(value)

    # returns a tuple of the components
    def components(self):
        nanoseconds = self.nanoseconds
        hours, nanoseconds = divmod(nanoseconds, unit.HR)
        minutes, nanoseconds = divmod(nanoseconds, unit.MIN)
        seconds, nanoseconds = divmod(nanoseconds, unit.SEC)
        return (hours, minutes, seconds, nanoseconds)

    def __str__(self):
        return '{:02d}:{:02d}:{:02d}.{:09d}'.format(*self.components())
