#!/usr/bin/python3

import sys

import sympy
from sympy.physics.units import *

import logging
import pdb
import copy

logging.basicConfig(level=logging.DEBUG)
LOG = logging.getLogger('algebra')

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
    def __init__(self, system, allow_invalid=False):
        self._system = system
        self._given = {}
        self._allow_invalid = allow_invalid
        self._cache = {}

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

class Point(object):
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y

    def __str__(self):
        return str((self.x, self.y))

    def __repr__(self):
        return repr((self.x, self.y))

class Circle(object):
    RADIUS, DIAMETER, CIRCUMFERENCE, AREA = SYMBOLS = sympy.symbols(
            'radius diameter circumference area', nonnegative=True)
    SYSTEM = System([
            sympy.Eq(DIAMETER, 2 * RADIUS),
            sympy.Eq(CIRCUMFERENCE, 2 * sympy.pi * RADIUS),
            sympy.Eq(AREA, sympy.pi * RADIUS**2),
            ], SYMBOLS)

    def __init__(self, **kw):
        self._solver = Solver(self.__class__.SYSTEM)
        self.set = self._solver.set
        self.set(**kw)

    def radius(self):
        return self._solver.get_symbol_single(self.__class__.RADIUS)

    def diameter(self):
        return self._solver.get_symbol_single(self.__class__.DIAMETER)

    def circumference(self):
        return self._solver.get_symbol_single(self.__class__.CIRCUMFERENCE)

    def area(self):
        return self._solver.get_symbol_single(self.__class__.AREA)

    # 0 degrees == right center, progressing counter-clockwise
    def point(self, radians):
        radius = self.radius()
        return Point(radius * sympy.cos(radians), radius * sympy.sin(radians))

class Cylinder(object):
    RADIUS, DIAMETER, HEIGHT, AREA, VOLUME = SYMBOLS = sympy.symbols(
            'radius diameter height area volume', nonnegative=True)

    SYSTEM = System([
            sympy.Eq(DIAMETER, 2 * RADIUS),
            sympy.Eq(AREA, 2 * sympy.pi * RADIUS * (HEIGHT + RADIUS)),
            sympy.Eq(VOLUME, sympy.pi * RADIUS**2 * HEIGHT)
            ], SYMBOLS)

    def __init__(self, **kw):
        self._solver = Solver(self.__class__.SYSTEM)
        self.set = self._solver.set
        self.set(**kw)

    def radius(self):
        return self._solver.get_symbol_single(self.__class__.RADIUS)

    def diameter(self):
        return self._solver.get_symbol_single(self.__class__.DIAMETER)

    def height(self):
        return self._solver.get_symbol_single(self.__class__.HEIGHT)

    def area(self):
        return self._solver.get_symbol_single(self.__class__.AREA)

    def volume(self):
        return self._solver.get_symbol_single(self.__class__.VOLUME)

    def circle(self):
        return Circle(radius=self.radius())

def main():

    LOG.debug('Processing systems.')
    Circle.SYSTEM.process()
    Cylinder.SYSTEM.process()
    LOG.debug('Processing complete.')

    x = Circle(area=25 * sympy.pi)
    print(x.radius())
    x = Cylinder(radius=5, height=2)
    x.area()
    import pdb
    pdb.set_trace()
    return 0

if __name__ == '__main__':
    sys.exit(main())
