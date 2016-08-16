#!/usr/bin/python3

import sys

import sympy
from sympy.physics.units import *

import logging
import pdb
import copy
import re

logging.basicConfig(level=logging.DEBUG)
LOG = logging.getLogger('algebra')


# Simple class to allow multiplying and dividing to transform values via an
# equation.  This is primarily useful for offset units, which are natively
# unsupported by sympy afaik.
class EqUnit(object):
    _REAL_VALUE = sympy.symbols('__EqUnit_REAL_VALUE__')
    VALUE = sympy.symbols('__EqUnit_VALUE__')
    def __init__(self, equation):
        # TODO: make sure VALUE is in the equation
        self._equation = equation

        try:
            reverse = solve(
                    Eq(EqUnit._REAL_VALUE, self._equation), EqUnit.VALUE,
                    dict=True)
            self._reverse_equation = reverse[0][EqUnit.VALUE]
        except:
            logging.warning('Equation irreversible: %s' % self._equation)
            self._reverse_equation = None


    def __rmul__(self, other):
        return self._equation.xreplace({EqUnit.VALUE: other})

    def __rtruediv__(self, other):
        if self._reverse_equation is None:
            raise RuntimeError('Equation irreversible: %s' % self._equation)
        return self._reverse_equation.xreplace({EqUnit._REAL_VALUE: other})

mod_360 = EqUnit(EqUnit.VALUE % (360*deg))
btdc = EqUnit(90 * deg + EqUnit.VALUE)
atdc = EqUnit(90 * deg - EqUnit.VALUE)
bbdc = EqUnit(270 * deg + EqUnit.VALUE)
abdc = EqUnit(270 * deg - EqUnit.VALUE)

ci = inch**3
cc = cm**3
crank_deg = deg
cam_deg = 2 * crank_deg

def get_set(somedict, key, value):
    current = somedict.get(key)
    if current is None:
        somedict[key] = value
        return value
    return current

def extra_item_dict(data, key, value):
    result = dict(data)
    result[key] = value
    return result

def iter_nonstring(value):
    if not isinstance(value, str) and hasattr(value, '__iter__'):
        return value
    return (value,)

# stages equation additions to reduce script start time
class Association(object):
    def __init__(self):
        self._mappings = {}

    def add(self, values):
        values = iter_nonstring(values)
        # get the collection of all mappings the values referenced have
        group = {value
                for key in values if key in self._mappings
                for value in self._mappings[key]}
        # add these values explicitly to it
        group.update(values)
        # assign the group to every value within the group
        self._mappings.update({key: group for key in group})

    def get(self, value):
        return self._mappings.get(value, {value})


class Equation(object):
    def __init__(self, equation):
        self._original = equation

        self._solved_for = {}
        for symbol in self.symbols():
            solution = sympy.solve(self.original(), symbol)
            if solution:
                self._solved_for[symbol] = solution

    def original(self):
        return self._original

    def solved_for(self, symbol):
        return self._solved_for.get(symbol)

    def solvable(self):
        return self._solved_for.keys()

    def symbols(self):
        return self.original().free_symbols

    def __repr__(self):
        return '{}={}'.format(self.original().lhs, self.original().rhs)

    def __str__(self):
        return repr(self)

class System(object):
    def __init__(self, eqs = None, symbols = None):
        if symbols is None:
            symbols = []
        if eqs is None:
            eqs = []


        self._eq_mapping_for = {}
        self._symbols = set()
        self._name_to_symbol = {}
        self._unprocessed_eqs = []
        self._associations = Association()

        self._add_symbols(symbols)
        self.stage(eqs)

    def process(self):
        for eq in self._unprocessed_eqs:
            self._add(eq)
        self._unprocessed_eqs = []

    def _add_symbols(self, symbols):
        for symbol in symbols:
            self._symbols.add(symbol)
            if get_set(self._name_to_symbol, symbol.name, symbol) != symbol:
                raise ValueError('Duplicate symbol with different flags.')

    def lookup_symbol(self, name):
        self.process()
        return self._name_to_symbol.get(name)

    def is_valid_symbol(self, symbol):
        self.process()
        return symbol in self._symbols

    def stage(self, eqs):
        eqs = iter_nonstring(eqs)
        self._unprocessed_eqs.extend(eqs)

    def add(self, eqs):
        self.stage(eqs)
        self.process()

    def _add(self, eq):
        equation = Equation(eq)
        symbols = equation.symbols()
        # keep track of which variables contribute to the calculations of
        # which others
        self._associations.add(symbols)
        # store the symbols
        self._add_symbols(symbols)

        for symbol in equation.solvable():
            for solution in equation.solved_for(symbol):
                get_set(get_set(self._eq_mapping_for, symbol, {}),
                        solution, set()).add(equation)

    def associated(self, symbol):
        self.process()
        return self._associations.get(symbol)

    def eq_mapping_for(self, symbol):
        self.process()
        return self._eq_mapping_for.get(symbol, {})

class Solver(object):
    def __init__(self, system, allow_invalid=False, **kw):
        self._system = system
        self._given = {}
        self._allow_invalid = allow_invalid
        self._cache = {}

        self.set(**kw)

    @staticmethod
    def validate(symbol, value):
        return sympy.solvers.check_assumptions(value, **symbol.assumptions0)

    def _check_symbol(self, symbol):
        if not self._system.is_valid_symbol(symbol):
            if not self._allow_invalid:
                raise ValueError('Invalid symbol specified.')
            return False
        return True

    def _symbol(self, name):
        symbol = self._system.lookup_symbol(name)
        if symbol is None:
            symbol = sympy.Symbol(name)
        return symbol

    def clear(self):
        self._cache.clear()
        self._given.clear()

    def given(self):
        return dict(self._given)

    def set(self, **kw):
        for key, value in kw.items():
            self.set_name(key, value)

    def set_name(self, name, value):
        self.set_symbol(self._symbol(name), value)

    def set_symbol(self, symbol, value):
        clear_associated_cache = False
        self._check_symbol(symbol)

        if value is None:
            try:
                del self._given[symbol]
                clear_associated_cache = True
            except:
                pass
        else:
            if not Solver.validate(symbol, value):
                raise ValueError('"{}" has assumptions that "{}" does not'
                        ' meet.'.format(symbol, value))

            if self._given.get(symbol) != value:
                self._given[symbol] = value
                clear_associated_cache = True
        if clear_associated_cache:
            for symbol in self._system.associated(symbol):
                try:
                    del self._cache[symbol]
                except:
                    pass

    def get_symbol(self, symbol, trace=False):
        result = self._get(symbol, set())
        if result and not trace:
            return set(result.keys())
        return result

    def get_symbol_single(self, symbol):
        result = self.get_symbol(symbol)
        if result:
            count = len(result)
            if count > 1:
                raise ValueError('Multiple solutions for "{}": {}'.format(
                    symbol, result))
            elif count == 1:
                return result.pop()
        raise ValueError('No solutions for "{}"'.format(symbol))

    def get_name(self, name, trace=False):
        return self.get_symbol(self._symbol(name), trace=trace)

    def get_name_single(self, name):
        return self.get_symbol_single(self._symbol(name))

    # calculates a set of all values deducible from the provided equations.
    # if your equations are inconsistent, this code will not care.
    def _get(self, symbol, visited):
        valid_symbol = self._check_symbol(symbol)

        cached = self._cache.get(symbol)
        if cached is not None:
            LOG.debug('Returning cached value for {}'.format(symbol))
            solutions = cached
        else:
            do_cache = True
            solutions = {}
            if symbol in self._given:
                value = self._given[symbol]
                get_set(solutions, value, {})[symbol] = value
            if valid_symbol:
                for eq, equations in self._system.eq_mapping_for(
                        symbol).items():
                    EQ_STRING = '{}={}'.format(symbol, eq)
                    LOG.debug('-- {} from {}'.format(EQ_STRING, equations))
                    if eq.free_symbols.intersection(visited):
                        LOG.debug('Equation depends upon a value that was'
                                ' already visited; skipping: {}'.format(
                                        EQ_STRING))
                        # because this solution depends upon the provided
                        # solution, we know that the result here will be
                        # incomplete, so do not cache it.  We could
                        # potentially go back and calculate this at the end,
                        # but it is unnecessary as we might might need this
                        # value yet and thus shouldn't calculate it.
                        do_cache = False
                        continue
                    next_visited = visited.union({symbol})

                    value_combinations = [ dict() ]
                    for unvisited in eq.free_symbols.difference(visited):
                        solution = self._get(unvisited, next_visited)
                        if solution is None:
                            LOG.debug('No solution found for {},'
                                    ' skipping.'.format(unvisited))
                            value_combinations.clear()
                            break
                        LOG.debug('Found: {}={}'.format(unvisited, solution))
                        # This rebuilds value_combinations each time, building
                        # upon the previous result.
                        value_combinations = [extra_item_dict(
                                combo, unvisited, item)
                                for combo in value_combinations
                                for item in solution.items()]
                    if value_combinations:
                        # +/- sqrt will have already been separated
                        for combo in value_combinations:
                            flat_combo = {key:item[0] for key, item in
                                combo.items()}
                            value = eq.xreplace(flat_combo)
                            get_set(get_set(solutions, value, {}), eq,
                                []).append(combo)
                            LOG.debug('Added solution: {}={} using {}'.format(
                                EQ_STRING, value, combo))
            # Check assumptions on the symbols
            invalid_solutions = {key for key in solutions.keys()
                    if not Solver.validate(symbol, key)}
            if invalid_solutions:
                LOG.debug('Removing invalid solutions: {}'.format(
                        invalid_solutions))
                for key in invalid_solutions:
                    del solutions[key]
            if do_cache:
                self._cache[symbol] = solutions
        return solutions if solutions else None

# Metaclass to add acessors for SYMBOLS, using _solver
class SymbolAccessor(type):
    def __new__(cls, clsname, superclasses, attributedict):
        new_class = type.__new__(cls, clsname, superclasses, attributedict)
        for symbol in getattr(new_class, 'SYMBOLS', ()):
            setattr(new_class, symbol.name, property(
                (lambda symbol: lambda self:
                        self._solver.get_symbol_single(symbol))(symbol),
                (lambda symbol: lambda self, value:
                        self._solver.set_symbol(symbol, value))(symbol)
                ))
        setattr(new_class, 'given', property(
            lambda self: self._solver.given()))
        return new_class

class Point(object):
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y

    def __str__(self):
        return str((self.x, self.y))

    def __repr__(self):
        return repr((self.x, self.y))

class Circle(metaclass=SymbolAccessor):
    RADIUS, DIAMETER, CIRCUMFERENCE, AREA = SYMBOLS = sympy.symbols(
            'radius diameter circumference area', nonnegative=True)
    SYSTEM = System([
            sympy.Eq(DIAMETER, 2 * RADIUS),
            sympy.Eq(CIRCUMFERENCE, 2 * sympy.pi * RADIUS),
            sympy.Eq(AREA, sympy.pi * RADIUS**2),
            ], SYMBOLS)

    def __init__(self, **kw):
        self._solver = Solver(self.__class__.SYSTEM, **kw)

    # 0 degrees == right center, progressing counter-clockwise
    def point(self, radians):
        radius = self.radius
        return Point(radius * sympy.cos(radians), radius * sympy.sin(radians))

class Cylinder(metaclass=SymbolAccessor):
    RADIUS, DIAMETER, HEIGHT, AREA, VOLUME = SYMBOLS = sympy.symbols(
            'radius diameter height area volume', nonnegative=True)
    SYSTEM = System([
            sympy.Eq(DIAMETER, 2 * RADIUS),
            sympy.Eq(AREA, 2 * sympy.pi * RADIUS * (HEIGHT + RADIUS)),
            sympy.Eq(VOLUME, sympy.pi * RADIUS**2 * HEIGHT)
            ], SYMBOLS)

    def __init__(self, **kw):
        self._solver = Solver(self.__class__.SYSTEM, **kw)

    @property
    def circle(self):
        return Circle(radius=self.radius)

class RightTriangle(metaclass=SymbolAccessor):
    SIDE_A, SIDE_B, HYPOTENUSE = SYMBOLS = sympy.symbols(
            'side_a side_b hypotenuse', nonnegative=True)
    SYSTEM = System([
            sympy.Eq(HYPOTENUSE**2, SIDE_A**2 + SIDE_B**2)
            ], SYMBOLS)

    def __init__(self, **kw):
        self._solver = Solver(self.__class__.SYSTEM, **kw)


class Tire(metaclass=SymbolAccessor):
    WIDTH, SIDEWALL, RIM, ASPECT_RATIO, DIAMETER = SYMBOLS = sympy.symbols(
            'width sidewall rim aspect_ratio diameter', nonnegative=True)
    SYSTEM = System([
            sympy.Eq(DIAMETER, RIM + SIDEWALL * 2),
            sympy.Eq(SIDEWALL, WIDTH * ASPECT_RATIO / 100),
            ], SYMBOLS)

    def __init__(self, **kw):
        self._solver = Solver(Tire.SYSTEM, **kw)

    @staticmethod
    def fromString(value):
        parts = re.split('/| *[rR]',value)
        if len(parts) == 3:
            width = parts[0]
            aspect_ratio = parts[1]
            rim = parts[2]
            if width.isdigit() and aspect_ratio.isdigit() and rim.isdigit():
                return Tire(width=int(width)*mm,
                        aspect_ratio=int(aspect_ratio),
                        rim=int(rim)*inch)
        raise RuntimeError('Bad format.')

    @property
    def cylinder(self):
        return Cylinder(diameter=self.diameter)

class CamShaft(object):
    INTAKE_OPEN, INTAKE_CLOSE, INTAKE_DURATION = sympy.symbols(
            'intake_open intake_close intake_duration')
    EXHAUST_OPEN, EXHAUST_CLOSE, EXHAUST_DURATION = sympy.symbols(
            'exhaust_open exhaust_close exhaust_duration')
    INTAKE_CENTERLINE, EXHAUST_CENTERLINE = sympy.symbols(
            'intake_centerline exhaust_centerline')
    LOBE_SEPARATION_ANGLE = sympy.symbols('lobe_separation_angle')
    ADVERTISED_INTAKE_OPEN, ADVERTISED_INTAKE_CLOSE = sympy.symbols(
            'advertised_intake_open advertised_intake_close')
    ADVERTISED_EXHAUST_OPEN, ADVERTISED_EXHAUST_CLOSE = sympy.symbols(
            'advertised_exhaust_open advertised_exhaust_close')
    ADVERTISED_INTAKE_DURATION, ADVERTISED_EXHAUST_DURATION = sympy.symbols(
            'advertised_intake_duration advertised_exhaust_duration')

    SYSTEM = System([
            # The (open - close) logic seems backwards intuitively, but it is
            # this way because the circle's degrees advance counter-clockwise,
            # but the crankshaft spins clockwise.
            sympy.Eq(INTAKE_DURATION, INTAKE_OPEN - INTAKE_CLOSE),
            sympy.Eq(EXHAUST_DURATION, EXHAUST_OPEN - EXHAUST_CLOSE),
            sympy.Eq(ADVERTISED_INTAKE_DURATION,
                    ADVERTISED_INTAKE_OPEN - ADVERTISED_INTAKE_CLOSE),
            sympy.Eq(ADVERTISED_EXHAUST_DURATION,
                    ADVERTISED_EXHAUST_OPEN - ADVERTISED_EXHAUST_CLOSE),

            # Assumes a camshaft with symmetric lobes, centering the duration
            # about the centerline..
            sympy.Eq(ADVERTISED_INTAKE_OPEN, INTAKE_CENTERLINE +
                ADVERTISED_INTAKE_DURATION / 2),
            sympy.Eq(ADVERTISED_INTAKE_CLOSE, INTAKE_CENTERLINE -
                ADVERTISED_INTAKE_DURATION / 2),

            sympy.Eq(ADVERTISED_EXHAUST_OPEN, EXHAUST_CENTERLINE +
                ADVERTISED_EXHAUST_DURATION / 2),
            sympy.Eq(ADVERTISED_EXHAUST_CLOSE, EXHAUST_CENTERLINE -
                ADVERTISED_EXHAUST_DURATION / 2),

            sympy.Eq(LOBE_SEPARATION_ANGLE, (EXHAUST_CENTERLINE -
                INTAKE_CENTERLINE)),
            ])
    # All values provided, other than the advertised durations, should be
    # figures obtained at 0.050" tappet lift or the math won't work.
    def __init__(self, **kw):
        self._solver = Solver(CamShaft.SYSTEM, allow_invalid=True, **kw)

    def advance(self):
        # if this is positive, the cam is advanced
        # if this is 0, the cam is "straight up"
        # if this is negative, the cam is retarded
        return self.lobe_separation_angle - self.intake_centerline
#for symbol in Tire.SYMBOLS:
#    setattr(Tire,symbol.name,property((lambda symbol: lambda self:
#        self._solver.get_symbol_single(symbol))(symbol)))

def main():

    LOG.debug('Processing systems.')
    CamShaft.SYSTEM.process()
    LOG.debug('Processing complete.')

    x = CamShaft(
            intake_centerline=sympy.Rational(106) * crank_deg * atdc,
            intake_open=sympy.Rational(3.5) * crank_deg * btdc,
            intake_close=sympy.Rational(35.5) * crank_deg * abdc,
            intake_duration=219 * crank_deg,
            advertised_intake_duration=271 * crank_deg,

            exhaust_open=sympy.Rational(51.5) * crank_deg * bbdc,
            exhaust_close=sympy.Rational(-4.5) * crank_deg * atdc,
            exhaust_duration=227 * crank_deg,
            advertised_exhaust_duration=279 * crank_deg,

            lobe_separation_angle=112 * cam_deg,

            gross_intake_valve_lift=sympy.Rational(0.515) * inch,
            gross_exhaust_valve_list=sympy.Rational(0.530) * inch,
            intake_rocker_ratio=sympy.Rational(1.5) * inch,
            exhaust_rocker_ratio=sympy.Rational(1.5) * inch,
            intake_valve_adjustment=0 * inch,
            exhaust_valve_adjustment=0 * inch,
            )

    import pdb
    pdb.set_trace()
    return 0

    LOG.debug('Processing systems.')
    Circle.SYSTEM.process()
    Cylinder.SYSTEM.process()
    RightTriangle.SYSTEM.process()
    Tire.SYSTEM.process()
    LOG.debug('Processing complete.')
    x = Circle(area=25 * sympy.pi)
    print(x.radius)
    x = Cylinder(radius=5, height=2)
    print(x.area)
    x = RightTriangle(side_a=3, side_b=4)
    print(x.hypotenuse)
    x = RightTriangle(side_a=3, hypotenuse=5)
    print(x.side_b)
    x = Tire.fromString('235/60 R15')
    print(x.width)
    print(x.cylinder.circle.circumference)
    import pdb
    pdb.set_trace()
    return 0

if __name__ == '__main__':
    sys.exit(main())



#    def exhaust_centerline(self):
#        return self.get('exhaust_centerline') / btdc * mod_360 / crank_deg
#    def exhaust_open(self):
#        return self.get('exhaust_open') / bbdc * mod_360 / crank_deg
#    def exhaust_close(self):
#        return self.get('exhaust_close') / atdc * mod_360 / crank_deg
#    def exhaust_duration(self):
#        return self.get('exhaust_duration') * mod_360 / crank_deg
#    def advertised_exhaust_open(self):
#        return self.get('advertised_exhaust_open') / bbdc * mod_360 / crank_deg
#    def advertised_exhaust_close(self):
#        return self.get('advertised_exhaust_close') / atdc * mod_360 / crank_deg
#    def advertised_exhaust_duration(self):
#        return self.get('advertised_exhaust_duration') * mod_360 / crank_deg
#    def intake_centerline(self):
#        return self.get('intake_centerline') / atdc * mod_360 / crank_deg
#    def intake_open(self):
#        return self.get('intake_open') / btdc * mod_360 / crank_deg
#    def intake_close(self):
#        return self.get('intake_close') / abdc * mod_360 / crank_deg
#    def intake_duration(self):
#        return self.get('intake_duration') * mod_360 / crank_deg
#    def advertised_intake_open(self):
#        return self.get('advertised_intake_open') / btdc * mod_360 / crank_deg
#    def advertised_intake_close(self):
#        return self.get('advertised_intake_close') / abdc * mod_360 / crank_deg
#    def advertised_intake_duration(self):
#        return self.get('advertised_intake_duration') * mod_360 / crank_deg
#    def lobe_separation_angle(self):
#        return self.get('lobe_separation_angle') * mod_360 / cam_deg

