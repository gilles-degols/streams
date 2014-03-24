# -*- coding: utf-8 -*-


###############################################################################


from __future__ import division

from collections import Iterable, Sized
from heapq import nlargest, nsmallest, heappush, heappop
from itertools import chain, islice, repeat
from operator import add, truediv
from re import compile as regex_compile

from six import iteritems, advance_iterator

# noinspection PyUnresolvedReferences
from six.moves import filter as ifilter, map as imap, reduce as reduce_func, \
    xrange as xxrange

from .iterators import seed, distinct, peek, accumulate, partly_distinct
from .poolofpools import PoolOfPools
from .utils import MaxHeapItem, filter_true, filter_false, value_mapper, \
    key_mapper, filter_keys, filter_values, make_list, int_or_none, \
    float_or_none, long_or_none, decimal_or_none, unicode_or_none


###############################################################################


class Stream(Iterable, Sized):

    WORKERS = PoolOfPools()
    SENTINEL = object()

    @classmethod
    def concat(cls, *streams):
        return cls(streams).chain()

    @classmethod
    def iterate(cls, function, seed_value):
        return cls(seed(function, seed_value))

    @classmethod
    def range(cls, *args, **kwargs):
        return cls(xxrange(*args, **kwargs))

    def __init__(self, iterator):
        if isinstance(iterator, dict):
            self.iterator = iteritems(iterator)
        else:
            self.iterator = iter(iterator)

    # noinspection PyTypeChecker
    def __len__(self):
        return len(self.iterator)

    def __iter__(self):
        return iter(self.iterator)

    def __reversed__(self):
        return self.reversed()

    @property
    def first(self):
        first_element = advance_iterator(self.iterator)
        self.iterator = chain([first_element], self.iterator)
        return first_element

    def _filter(self, condition, predicate, **concurrency_kwargs):
        mapper = self.WORKERS.get(concurrency_kwargs)
        if mapper:
            iterator = ((predicate, item) for item in self)
            filtered = mapper(condition, iterator)
            filtered = (result for suitable, result in filtered if suitable)
        else:
            filtered = ifilter(predicate, self)
        return self.__class__(filtered)

    def filter(self, predicate, **concurrency_kwargs):
        return self._filter(filter_true, predicate, **concurrency_kwargs)

    def exclude(self, predicate, **concurrency_kwargs):
        return self._filter(filter_false, predicate, **concurrency_kwargs)

    def regexp(self, regexp, flags=0):
        regexp = regex_compile(regexp, flags)
        return self.filter(regexp.match)

    def divisible_by(self, number):
        return self.filter(lambda item: item % number == 0)

    def evens(self):
        return self.divisible_by(2)

    def odds(self):
        return self.filter(lambda item: item % 2 != 0)

    def instances_of(self, cls):
        return self.filter(lambda item: isinstance(item, cls))

    def exclude_nones(self):
        return self.filter(lambda item: item is not None)

    def only_trues(self):
        return self.filter(bool)

    def only_falses(self):
        return self.filter(lambda item: not bool(item))

    def only_nones(self):
        return self.filter(lambda item: item is None)

    def ints(self):
        return self.map(int_or_none).exclude_nones()

    def floats(self):
        return self.map(float_or_none).exclude_nones()

    def longs(self):
        return self.map(long_or_none).exclude_nones()

    def decimals(self):
        return self.map(decimal_or_none).exclude_nones()

    def strings(self):
        return self.map(unicode_or_none).exclude_nones()

    def tuplify(self, clones=2):
        return self.__class__(tuple(repeat(item, clones)) for item in self)

    def map(self, predicate, **concurrency_kwargs):
        mapper = self.WORKERS.get(concurrency_kwargs)
        if not mapper:
            mapper = imap
        return self.__class__(mapper(predicate, self))

    def _kv_map(self, mapper, predicate, **concurrency_kwargs):
        iterator = ((predicate, item) for item in self)
        stream = self.__class__(iterator)
        return stream.map(mapper, **concurrency_kwargs)

    def value_map(self, predicate, **concurrency_kwargs):
        return self._kv_map(value_mapper, predicate, **concurrency_kwargs)

    def key_map(self, predicate, **concurrency_kwargs):
        return self._kv_map(key_mapper, predicate, **concurrency_kwargs)

    def distinct(self):
        return self.__class__(distinct(self))

    def partly_distinct(self):
        return self.__class__(partly_distinct(self))

    def sorted(self, key=None, reverse=False):
        return self.__class__(sorted(self, reverse=reverse, key=key))

    def reversed(self):
        try:
            iterator = reversed(self.iterator)
        except TypeError:
            iterator = reversed(list(self.iterator))
        return self.__class__(iterator)

    def peek(self, predicate):
        return self.__class__(peek(self, predicate))

    def limit(self, size):
        return self.__class__(islice(self, size))

    def skip(self, size):
        return self.__class__(islice(self, size, None))

    def keys(self):
        return self.map(filter_keys)

    def values(self):
        return self.map(filter_values)

    def chain(self):
        return self.__class__(chain.from_iterable(self))

    def largest(self, size):
        return self.__class__(nlargest(size, self))

    def smallest(self, size):
        return self.__class__(nsmallest(size, self))

    def reduce(self, function, initial=None):
        iterator = iter(self)
        if initial is None:
            initial = advance_iterator(iterator)
        return reduce_func(function, iterator, initial)

    def sum(self):
        iterator = accumulate(self, add)
        last = advance_iterator(iterator)
        for item in iterator:
            last = item
        return last

    def count(self, element=SENTINEL):
        if element is not self.SENTINEL:
            return sum((1 for item in self if item is element))
        if hasattr(self.iterator, "__len__"):
            # noinspection PyTypeChecker
            return len(self.iterator)
        return sum((1 for _ in self))

    def average(self):
        counter = 1
        iterator = iter(self)
        total = advance_iterator(iterator)
        for item in iterator:
            total = add(total, item)
            counter += 1
        return truediv(total, counter)

    def nth_element(self, nth):
        if nth == 1:
            return min(self)
        self.iterator = make_list(self.iterator)
        if nth <= len(self.iterator):
            return max(self.smallest(nth))

    def median(self):
        biggest, smallest = [], []
        iterator = iter(self)
        first_elements = list(islice(iterator, 2))
        if not first_elements:
            return None
        if len(first_elements) == 1:
            return first_elements[0]

        first, last = first_elements
        if first > last:
            first, last = last, first
        smallest.append(MaxHeapItem(first))
        biggest.append(last)

        for item in iterator:
            if item < smallest[0].value:
                heappush(smallest, MaxHeapItem(item))
            else:
                heappush(biggest, item)
            if len(smallest) > len(biggest) + 1:
                heappush(biggest, heappop(smallest).value)
            elif len(biggest) > len(smallest) + 1:
                heappush(smallest, MaxHeapItem(heappop(biggest)))

        biggest_item = max(biggest, smallest, key=len)[0]
        if isinstance(biggest_item, MaxHeapItem):
            return biggest_item.value
        return biggest_item

    def any(self, predicate=None, **concurrency_kwargs):
        if predicate is None:
            iterator = iter(self)
        else:
            iterator = self.map(predicate, **concurrency_kwargs)
        return any(iterator)

    def all(self, predicate=None, **concurrency_kwargs):
        if predicate is None:
            iterator = iter(self)
        else:
            iterator = self.map(predicate, **concurrency_kwargs)
        return all(iterator)
