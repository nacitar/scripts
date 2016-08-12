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

def value_combinations(dictionary):
    if dictionary:
        combinations = [ dict() ]
        for (key, values) in dictionary.items():
            combinations = [extra_item_dict(combo, key, value)
                    for combo in combinations
                    for value in iter_nonstring(values)]
        return combinations
    return []

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

class System(object):
    def __init__(self, equations = None, symbols = None):
        if symbols is None:
            symbols = []
        if equations is None:
            equations = []

        self._symbol_equations = {}
        self._symbols = set(symbols)
        self._unprocessed_equations = []
        self._associations = Association()
        self.stage(equations)

    def process(self):
        for equation in self._unprocessed_equations:
            self._add(equation)
        self._unprocessed_equations = []

    def is_valid_symbol(self, symbol):
        self.process()
        return symbol in self._symbols

    def stage(self, equations):
        equations = iter_nonstring(equations)
        self._unprocessed_equations.extend(equations)

    def add(self, equations):
        self.stage(equations)
        self.process()

    def _add(self, equation):
        symbols = equation.free_symbols
        # keep track of which variables contribute to the calculations of
        # which others
        self._associations.add(symbols)
        # store the symbols
        self._symbols.update(symbols)
        for symbol in symbols:
            # Solve the equation for all symbols present
            solutions = sympy.solve(equation, symbol)
            # set removes duplicate solutions for us
            get_set(self._symbol_equations, symbol, set()).update(solutions)

    def associated(self, symbol):
        self.process()
        return self._associations.get(symbol)

    def equations(self, symbol):
        self.process()
        return self._symbol_equations.get(symbol, set())

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

    def clear(self):
        self._cache.clear()
        self._given.clear()

    def set(self, symbol, value):
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

    def get(self, symbol):
        return self._get(symbol, set())

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
            solutions = set()
            if symbol in self._given:
                solutions.add(self._given[symbol])
            if valid_symbol:
                for equation in self._system.equations(symbol):
                    LOG.debug('-- {} = {}'.format(symbol, equation))
                    if equation.free_symbols.intersection(visited):
                        LOG.debug('Equation depends upon a value that was'
                                ' already visited; skipping: {} = {}'.format(
                                        symbol, equation))
                        # because this solution depends upon the provided
                        # solution, we know that the result here will be
                        # incomplete, so do not cache it.  We could
                        # potentially go back and calculate this at the end,
                        # but it is unnecessary as we might might need this
                        # value yet and thus shouldn't calculate it.
                        do_cache = False
                        continue
                    unvisited_solutions = {}
                    next_visited = visited.union({symbol})
                    for unvisited in equation.free_symbols.difference(visited):
                        solution = self._get(unvisited, next_visited)
                        if solution is None:
                            LOG.debug('No solution found for {},'
                                    ' skipping.'.format(unvisited))
                            unvisited_solutions.clear()
                            break
                        LOG.debug('Found: {} = {}'.format(unvisited, solution))
                        unvisited_solutions[unvisited] = solution
                    if unvisited_solutions:
                        new_solutions = {equation.xreplace(combo)
                                for combo in value_combinations(
                                        unvisited_solutions)}
                        solutions.update(new_solutions)
                        LOG.debug('Added solutions: {} = {} = {}'.format(
                            symbol, equation, new_solutions))
            # Check assumptions on the symbols
            invalid_solutions = {solution for solution in solutions
                    if not Solver.validate(symbol, solution)}
            if invalid_solutions:
                LOG.debug('Removing invalid solutions: {}'.format(
                        invalid_solutions))
            solutions.difference_update(invalid_solutions)
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
    RADIUS, DIAMETER, CIRCUMFERENCE, AREA = sympy.symbols(
            'radius diameter circumference area', nonnegative=True)
    SYSTEM = System([
            sympy.Eq(DIAMETER, 2 * RADIUS),
            sympy.Eq(CIRCUMFERENCE, 2 * sympy.pi * RADIUS),
            sympy.Eq(AREA, sympy.pi * RADIUS**2)])

    def __init__(self, symbol, value):
        self._solver = Solver(self.__class__.SYSTEM)

        self._solver.set(symbol, value)

    def get(self, symbol):
        return self._solver.get(symbol)

    def radius(self):
        return self.get(self.__class__.RADIUS)

    def diameter(self):
        return self.get(self.__class__.DIAMETER)

    def circumference(self):
        return self.get(self.__class__.CIRCUMFERENCE)

    def area(self):
        return self.get(self.__class__.AREA)

    # 0 degrees == right center, progressing counter-clockwise
    def point(self, radians):
        return {Point(radius * sympy.cos(radians),
                radius * sympy.sin(radians)) for radius in self.radius()}

def main():

    LOG.debug('Processing systems.')
    Circle.SYSTEM.process()
    LOG.debug('Processing complete.')

    x = Circle(Circle.AREA, 25 * sympy.pi)
    print(x.get(Circle.RADIUS))
    import pdb
    pdb.set_trace()
    return 0

if __name__ == '__main__':
    sys.exit(main())
