# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import bpy

import math
import bisect

from .utils_python import sequence_startswith, sequence_endswith
from .utils_text import indent, longest_common_substring
from .bpy_inspect import prop

#============================================================================#

"""
Statistics/summaries: (more than one may be requested at once)
* Count
* Sum (= mean * count)
* Sum of squares (?) (= 2nd moment about zero * count)
* Product (= exp(log(v1) + log(v2) + ...))
* Min
* Max
* Range
* Center
* Moments? (0: total/sum, 1: average/mean, 2: variance, 3: skewness; etc.) Moments are about some point (usually zero or mean)
    * Standard deviation (sqrt(variance)), Variance? (stddev^2), Root mean square error?, Mean absolute deviation?, Mean square error?, Geometric standard deviation?, Harmonic stddev?
    * Average, Geometric Average?, Harmonic Mean?
* Sorted list(s) by certain parameter(s)
* Median
* Histogram/Frequency map
* Mode (for discrete/symbolic values, or if some sort of histogram can be built) (will it be useful to see what elements repeat exactly the given number of times?)
* Pattern (detect common parts or even some general pattern)
* Union (for enums/sets) -- all items ever encountered (equivalend of Max/Sum)
* Intersection (for enums/sets) -- only items encountered in each sample (equivalent of Min/Product)
* Symmetric Difference (for enums/sets) - only items encountered in a single sample (sort of antithesis of Mode)

Bool: treated as int
Int: all numerical summaries
Float: all numerical summaries, but instead of mode, kernel density estimation is used
Enum/Set: frequency map, mode, union, intersection, difference
String (ordered sequence?): sorted list (if elements are sortable), frequency map, mode, pattern (sort of similar to Intersection)
Object: frequency map, mode

Vectors can have per-component statistics and "holistic" statistics (when components are taken into account as a whole)
* Statistics of length/squared-length (Absolute? Euclidean? Manhattan?)
* Statistics of projection/dot-product/angle to a given vector
* Mode can, in principle, be calculated for vectors, but frequency map has to be of the corresponding dimension
* Normals are just normalized directions (maybe they should be handled on the user level?)
* There's not much we can do about Euler (3-Vector) or Angle-axis (a normal and an angle) besides the per-component statistics
* Quaternion should probably be converted to Matrix (there are no useful statistics about its components separately)
* Matrix can be treated as a set of vectors; the result is probably the separate vectors converted into Matrix again (and maybe orthogonalized?)

"""

class Aggregator:
    _count = None
    _same = None
    _prev = None
    
    _min = None
    _max = None
    
    _sum = None
    _sum_log = None
    _sum_rec = None
    _product = None
    
    _Ak = None
    _Qk = None
    
    _sorted = None
    
    _freq_map = None
    _freq_max = None
    _modes = None
    
    _union = None
    _intersection = None
    _difference = None
    
    _subseq = None
    _subseq_starts = None
    _subseq_ends = None
    
    # sum can be calculated from average, and product (for values > 0)
    # can be calculated from sum_log, but it won't be precise for ints
    
    type = property(lambda self: self._type)
    
    count = property(lambda self: self._count)
    same = property(lambda self: self._same)
    
    min = property(lambda self: self._min)
    max = property(lambda self: self._max)
    @property
    def range(self):
        if (self._max is None) or (self._min is None): return None
        return self._max - self._min
    @property
    def center(self):
        if (self._max is None) or (self._min is None): return None
        return (self._max + self._min) * 0.5
    
    sum = property(lambda self: self._sum)
    sum_log = property(lambda self: self._sum_log)
    sum_rec = property(lambda self: self._sum_rec)
    product = property(lambda self: self._product)
    
    @property
    def mean(self):
        return self._Ak
    @property
    def geometric_mean(self):
        if (self._sum_log is None) or (self._count is None): return None
        return math.exp(self._sum_log / self._count)
    @property
    def harmonic_mean(self):
        if (self._sum_rec is None): return None
        return 1.0 / self._sum_rec
    @property
    def variance(self):
        if (self._Qk is None) or (self._count is None): return None
        if self._count < 2: return 0.0
        return self._Qk / (self._count - 1)
    @property
    def stddev(self):
        if (self._Qk is None) or (self._count is None): return None
        if self._count < 2: return 0.0
        return math.sqrt(self._Qk / (self._count - 1))
    
    sorted = property(lambda self: self._sorted)
    @property
    def median(self):
        n = len(self._sorted)
        if (n % 2) == 1: return self._sorted[n // 2]
        i = n // 2
        return (self._sorted[i] + self._sorted[i - 1]) * 0.5
    
    freq_map = property(lambda self: self._freq_map)
    freq_max = property(lambda self: self._freq_max)
    modes = property(lambda self: self._modes)
    
    union = property(lambda self: self._union)
    intersection = property(lambda self: self._intersection)
    difference = property(lambda self: self._difference)
    
    subseq = property(lambda self: self._subseq)
    subseq_starts = property(lambda self: self._subseq_starts)
    subseq_ends = property(lambda self: self._subseq_ends)
    
    _numerical_queries = frozenset([
        'count', 'same', 'min', 'max', 'range', 'center',
        'sum', 'sum_log', 'sum_rec', 'product',
        'mean', 'geometric_mean', 'harmonic_mean', 'variance', 'stddev',
        'sorted', 'median', 'freq_map', 'freq_max', 'modes',
    ])
    _enum_queries = frozenset([
        'count', 'same',
        'freq_map', 'freq_max', 'modes',
        'union', 'intersection', 'difference',
    ])
    _sequence_queries = frozenset([
        'count', 'same',
        'sorted', 'median', 'freq_map', 'freq_max', 'modes',
        'subseq', 'subseq_starts', 'subseq_ends',
    ])
    _object_queries = frozenset([
        'count', 'same',
        'freq_map', 'freq_max', 'modes',
    ])
    _all_queries = {'NUMBER':_numerical_queries, 'ENUM':_enum_queries,
        'SEQUENCE':_sequence_queries, 'OBJECT':_object_queries}
    
    _compiled = {}
    
    def __init__(self, type, queries=None, convert=None):
        self._type = type
        
        self._startswith = sequence_startswith
        self._endswith = sequence_endswith
        if type == 'STRING':
            self._startswith = str.startswith
            self._endswith = str.endswith
            type = 'SEQUENCE'
        elif type == 'BOOL':
            if convert is None: convert = int
            type = 'NUMBER'
        
        if queries is None:
            queries = self._all_queries[type]
        elif isinstance(queries, str):
            queries = queries.split(" ")
        
        compiled_key0 = (type, frozenset(queries), convert)
        compiled = Aggregator._compiled.get(compiled_key0)
        
        if not compiled:
            queries = set(queries) # make sure it's a copy
            
            # make sure requirements are included
            if 'same' in queries: queries.add('prev')
            if ('range' in queries) or ('center' in queries): queries.update(('min', 'max'))
            if 'mean' in queries: queries.add('Ak')
            if 'geometric_mean' in queries: queries.update(('sum_log', 'count'))
            if 'harmonic_mean' in queries: queries.add('sum_rec')
            if ('variance' in queries) or ('stddev' in queries): queries.update(('Qk', 'count'))
            if 'Qk' in queries: queries.add('Ak')
            if 'Ak' in queries: queries.add('count')
            if 'median' in queries: queries.add('sorted')
            if 'modes' in queries: queries.add('freq_max')
            if 'freq_max' in queries: queries.add('freq_map')
            if queries.intersection(('subseq', 'subseq_starts', 'subseq_ends')):
                queries.update(('subseq', 'subseq_starts', 'subseq_ends'))
            
            compiled_key = (type, frozenset(queries), convert)
            compiled = Aggregator._compiled.get(compiled_key)
            
            if not compiled:
                compiled = self._compile(type, queries, convert)
                Aggregator._compiled[compiled_key] = compiled
            
            Aggregator._compiled[compiled_key0] = compiled
        
        # Assign bound methods
        self.reset = compiled[0].__get__(self, self.__class__)
        self._init = compiled[1].__get__(self, self.__class__)
        self._add = compiled[2].__get__(self, self.__class__)
        
        self.reset()
    
    def _compile(self, type, queries, convert):
        reset_lines = []
        init_lines = []
        add_lines = []
        
        localvars = dict(log=math.log, insort_left=bisect.insort_left,
            startswith=self._startswith, endswith=self._endswith, convert=convert)
        
        if 'count' in queries:
            reset_lines.append("self._count = None")
            init_lines.append("self._count = 1")
            add_lines.append("self._count += 1")
        if 'same' in queries:
            reset_lines.append("self._same = None")
            init_lines.append("self._same = True")
            add_lines.append("if self._same: self._same = (value == self._prev)")
        if 'prev' in queries:
            reset_lines.append("self._prev = None")
            init_lines.append("self._prev = value")
            add_lines.append("self._prev = value")
        
        if 'min' in queries:
            reset_lines.append("self._min = None")
            init_lines.append("self._min = value")
            add_lines.append("self._min = min(self._min, value)")
        if 'max' in queries:
            reset_lines.append("self._max = None")
            init_lines.append("self._max = value")
            add_lines.append("self._max = max(self._max, value)")
        
        if 'sum' in queries:
            reset_lines.append("self._sum = None")
            init_lines.append("self._sum = value")
            add_lines.append("self._sum += value")
        if 'sum_log' in queries:
            reset_lines.append("self._sum_log = None")
            init_lines.append("self._sum_log = (log(value) if value > 0.0 else 0.0)")
            add_lines.append("self._sum_log += (log(value) if value > 0.0 else 0.0)")
        if 'sum_rec' in queries:
            reset_lines.append("self._sum_rec = None")
            init_lines.append("self._sum_rec = (1.0 / value if value != 0.0 else 0.0)")
            add_lines.append("self._sum_rec += (1.0 / value if value != 0.0 else 0.0)")
        if 'product' in queries:
            reset_lines.append("self._product = None")
            init_lines.append("self._product = value")
            add_lines.append("self._product *= value")
        
        if 'Ak' in queries:
            reset_lines.append("self._Ak = None")
            init_lines.append("self._Ak = value")
            add_lines.append("delta = (value - self._Ak)")
            add_lines.append("self._Ak += delta / self._count")
        if 'Qk' in queries:
            reset_lines.append("self._Qk = None")
            init_lines.append("self._Qk = 0.0")
            add_lines.append("self._Qk += delta * (value - self._Ak)")
        
        if 'sorted' in queries:
            reset_lines.append("self._sorted = None")
            init_lines.append("self._sorted = [value]")
            add_lines.append("insort_left(self._sorted, value)")
        
        if type != 'ENUM':
            if 'freq_map' in queries:
                reset_lines.append("self._freq_map = None")
                init_lines.append("self._freq_map = {value:1}")
                add_lines.append("freq = self._freq_map.get(value, 0) + 1")
                add_lines.append("self._freq_map[value] = freq")
            if 'freq_max' in queries:
                reset_lines.append("self._freq_max = None")
                init_lines.append("self._freq_max = 0")
                add_lines.append("if freq > self._freq_max:")
                add_lines.append("    self._freq_max = freq")
            if 'modes' in queries:
                reset_lines.append("self._modes = None")
                init_lines.append("self._modes = []")
                add_lines.append("    self._modes = [value]")
                add_lines.append("elif freq == self._freq_max:")
                add_lines.append("    self._modes.append(value)")
        else:
            if 'freq_map' in queries:
                reset_lines.append("self._freq_map = None")
                init_lines.append("self._freq_map = {item:1 for item in value}")
                add_lines.append("for item in value:")
                add_lines.append("    freq = self._freq_map.get(item, 0) + 1")
                add_lines.append("    self._freq_map[item] = freq")
            if 'freq_max' in queries:
                reset_lines.append("self._freq_max = None")
                init_lines.append("self._freq_max = 0")
                add_lines.append("    if freq > self._freq_max:")
                add_lines.append("        self._freq_max = freq")
            if 'modes' in queries:
                reset_lines.append("self._modes = None")
                init_lines.append("self._modes = []")
                add_lines.append("        self._modes = [item]")
                add_lines.append("    elif freq == self._freq_max:")
                add_lines.append("        self._modes.append(item)")
        
        if 'union' in queries:
            reset_lines.append("self._union = None")
            init_lines.append("self._union = set(value)")
            add_lines.append("self._union.update(value)")
        if 'intersection' in queries:
            reset_lines.append("self._intersection = None")
            init_lines.append("self._intersection = set(value)")
            add_lines.append("self._intersection.intersection_update(value)")
        if 'difference' in queries:
            reset_lines.append("self._difference = None")
            init_lines.append("self._difference = set(value)")
            add_lines.append("self._difference.symmetric_difference_update(value)")
        
        if 'subseq' in queries:
            reset_lines.append("self._subseq = None")
            reset_lines.append("self._subseq_starts = None")
            reset_lines.append("self._subseq_ends = None")
            init_lines.append("self._subseq = value")
            init_lines.append("self._subseq_starts = True")
            init_lines.append("self._subseq_ends = True")
            add_lines.append("self._subseq_update(value)")
        
        reset_lines.append("self.add = self._init")
        reset_lines = [indent(line, "    ") for line in reset_lines]
        reset_lines.insert(0, "def reset(self):")
        reset_code = "\n".join(reset_lines)
        #print(reset_code)
        exec(reset_code, localvars, localvars)
        reset = localvars["reset"]
        
        if convert is not None: init_lines.insert(0, "value = convert(value)")
        init_lines.append("self.add = self._add")
        init_lines = [indent(line, "    ") for line in init_lines]
        init_lines.insert(0, "def _init(self, value):")
        init_code = "\n".join(init_lines)
        #print(init_code)
        exec(init_code, localvars, localvars)
        _init = localvars["_init"]
        
        if convert is not None: init_lines.insert(0, "value = convert(value)")
        add_lines = [indent(line, "    ") for line in add_lines]
        add_lines.insert(0, "def _add(self, value):")
        add_code = "\n".join(add_lines)
        #print(add_code)
        exec(add_code, localvars, localvars)
        _add = localvars["_add"]
        
        return reset, _init, _add
    
    def _subseq_update(self, value):
        if self._subseq_starts:
            if self._startswith(value, self._subseq):
                pass
            elif self._startswith(self._subseq, value):
                self._subseq = value
            else:
                self._subseq_starts = False
        if self._subseq_ends:
            if self._endswith(value, self._subseq):
                pass
            elif self._endswith(self._subseq, value):
                self._subseq = value
            else:
                self._subseq_ends = False
        if self._subseq and not (self._subseq_starts or self._subseq_ends):
            prev_subseq = self._subseq
            self._subseq = next(iter(longest_common_substring(self._subseq, value)), None) or value[0:0]
            if self._subseq:
                if self._startswith(prev_subseq, self._subseq):
                    self._subseq_starts = self._startswith(value, self._subseq)
                if self._endswith(prev_subseq, self._subseq):
                    self._subseq_ends = self._endswith(value, self._subseq)

class VectorAggregator:
    def __init__(self, size, type, queries=None, covert=None):
        self.axes = tuple(Aggregator(type, queries, covert) for i in range(size))
    
    def reset(self):
        for axis in self.axes: axis.reset()
    
    def __len__(self):
        return len(self.axes)
    
    def add(self, value):
        for axis, item in zip(self.axes, value): axis.add(item)
    
    type = property(lambda self: self.axes[0].type)
    
    count = property(lambda self: self.axes[0].count) # same for all
    same = property(lambda self: tuple(axis.same for axis in self.axes))
    
    min = property(lambda self: tuple(axis.min for axis in self.axes))
    max = property(lambda self: tuple(axis.max for axis in self.axes))
    range = property(lambda self: tuple(axis.range for axis in self.axes))
    center = property(lambda self: tuple(axis.center for axis in self.axes))
    
    sum = property(lambda self: tuple(axis.sum for axis in self.axes))
    sum_log = property(lambda self: tuple(axis.sum_log for axis in self.axes))
    sum_rec = property(lambda self: tuple(axis.sum_rec for axis in self.axes))
    product = property(lambda self: tuple(axis.product for axis in self.axes))
    
    mean = property(lambda self: tuple(axis.mean for axis in self.axes))
    geometric_mean = property(lambda self: tuple(axis.geometric_mean for axis in self.axes))
    harmonic_mean = property(lambda self: tuple(axis.harmonic_mean for axis in self.axes))
    variance = property(lambda self: tuple(axis.variance for axis in self.axes))
    stddev = property(lambda self: tuple(axis.stddev for axis in self.axes))
    
    sorted = property(lambda self: tuple(axis.sorted for axis in self.axes))
    median = property(lambda self: tuple(axis.median for axis in self.axes))
    
    freq_map = property(lambda self: tuple(axis.freq_map for axis in self.axes))
    freq_max = property(lambda self: tuple(axis.freq_max for axis in self.axes))
    modes = property(lambda self: tuple(axis.modes for axis in self.axes))
    
    union = property(lambda self: tuple(axis.union for axis in self.axes))
    intersection = property(lambda self: tuple(axis.intersection for axis in self.axes))
    difference = property(lambda self: tuple(axis.difference for axis in self.axes))
    
    subseq = property(lambda self: tuple(axis.subseq for axis in self.axes))
    subseq_starts = property(lambda self: tuple(axis.subseq_starts for axis in self.axes))
    subseq_ends = property(lambda self: tuple(axis.subseq_ends for axis in self.axes))

class aggregated(prop):
    def aggregate_make(self, value):
        prop_decl = self.make(value)
        
        aggregation_type = 'NUMBER'
        vector_size = 0
        convert = None
        
        prop_info = BpyProp(prop_decl)
        if prop_info.type in (bpy.props.BoolProperty, bpy.props.IntProperty, bpy.props.FloatProperty):
            if prop_info.type is bpy.props.BoolProperty: convert = int
        elif prop_info.type in (bpy.props.BoolVectorProperty, bpy.props.IntVectorProperty, bpy.props.FloatVectorProperty):
            if prop_info.type is bpy.props.BoolVectorProperty: convert = int
            vector_size = prop_info.get("size") or len(prop_info["default"])
        elif prop_info.type is bpy.props.CollectionProperty:
            aggregation_type = 'SEQUENCE'
        elif prop_info.type is bpy.props.EnumProperty:
            aggregation_type = 'ENUM'
        elif prop_info.type is bpy.props.StringProperty:
            aggregation_type = 'STRING'
        elif prop_info.type is bpy.props.PointerProperty:
            aggregation_type = 'OBJECT'
        
        default_queries = prop_info.get("queries")
        
        if vector_size == 0:
            @staticmethod
            def aggregator(queries=None):
                if queries is None: queries = default_queries
                return Aggregator(aggregation_type, queries, convert)
        else:
            @staticmethod
            def aggregator(queries=None):
                if queries is None: queries = default_queries
                return VectorAggregator(vector_size, aggregation_type, queries, convert)
        
        #@addon.PropertyGroup
        class AggregatePG:
            value = prop_decl
            same = True | prop()
            aggregator = aggregator
        AggregatePG.__name__ += ":AUTOREGISTER" # for AddonManager
        
        return AggregatePG | prop()
    
    __ror__ = aggregate_make
    __rlshift__ = aggregate_make
    __rrshift__ = aggregate_make






# TODO: documentation

class NumberAccumulator:
    count = 0
    result = None
    min = None
    max = None
    
    def __init__(self, mode):
        self._mode = mode
        self._init = getattr(self, mode + "_INIT")
        self._next = getattr(self, mode)
        self._calc = getattr(self, mode + "_CALC")
    
    def reset(self):
        for k in list(self.__dict__.keys()):
            if not k.startswith("_"):
                del self.__dict__[k]
    
    def copy(self):
        return NumberAccumulator(self._mode)
    
    def __len__(self):
        return self.count
    
    def add(self, value):
        self.count = 1
        self.min = value
        self.max = value
        self.add = self._add
        self._init(value)
    
    def _add(self, value):
        self.count += 1
        self.min = min(self.min, value)
        self.max = max(self.max, value)
        self._next(value)
    
    def calc(self):
        return self._calc()
    
    def same(self, tolerance=1e-6):
        if self.count == 0:
            return True
        return (self.max - self.min) < tolerance
    
    # utility function
    @staticmethod
    def _median(values):
        n = len(values)
        if (n % 2) == 1:
            return values[n // 2]
        else:
            i = n // 2
            return (values[i] + values[i - 1]) * 0.5
    # ====================================================== #
    
    def AVERAGE_INIT(self, value):
        self.Ak = value
    def AVERAGE(self, value):
        Ak_1 = self.Ak
        self.Ak = Ak_1 + (value - Ak_1) / self.count
    def AVERAGE_CALC(self):
        if self.count > 0:
            self.result = self.Ak
        yield
    
    def STDDEV_INIT(self, value):
        self.Ak = value
        self.Qk = 0.0
    def STDDEV(self, value):
        Ak_1 = self.Ak
        self.Ak = Ak_1 + (value - Ak_1) / self.count
        self.Qk = self.Qk + (value - Ak_1) * (value - self.Ak)
    def STDDEV_CALC(self):
        if self.count > 0:
            self.result = math.sqrt(self.Qk / self.count)
        yield
    
    def MEDIAN_INIT(self, value):
        self.values = [value]
    def MEDIAN(self, value):
        bisect.insort_left(self.values, value)
    def MEDIAN_CALC(self):
        if self.count > 0:
            self.result = self._median(values)
        yield
    
    def MODE_INIT(self, value):
        self.values = [value]
    def MODE(self, value):
        bisect.insort_left(self.values, value)
    def MODE_CALC(self):
        if self.count <= 0:
            return
        
        values = self.values
        n = len(values)
        
        # Divide the range to n bins of equal width
        neighbors = [0] * n
        sigma = (self.max - self.min) / (n - 1)
        
        mode = 0
        for i in range(n):
            v = values[i] # position of current item
            density = neighbors[i] # density of preceding neighbors
            
            # Find+add density of subsequent neighbors
            for j in range(i + 1, n):
                yield
                dv = sigma - abs(v - values[j])
                if dv <= 0:
                    break
                neighbors[j] += dv
                density += dv
            
            if density > mode:
                mode = density
                modes = [v]
            elif (density != 0) and (density == mode):
                modes.append(v)
        
        if mode == 0:
            # All items have same density
            self.result = (self.max + self.min) * 0.5
        else:
            self.result = self._median(modes)
    
    def RANGE_INIT(self, value):
        pass
    def RANGE(self, value):
        pass
    def RANGE_CALC(self):
        if self.count > 0:
            self.result = (self.max - self.min)
        yield
    
    def CENTER_INIT(self, value):
        pass
    def CENTER(self, value):
        pass
    def CENTER_CALC(self):
        if self.count > 0:
            self.result = (self.min + self.max) * 0.5
        yield
    
    def MIN_INIT(self, value):
        pass
    def MIN(self, value):
        pass
    def MIN_CALC(self):
        if self.count > 0:
            self.result = self.min
        yield
    
    def MAX_INIT(self, value):
        pass
    def MAX(self, value):
        pass
    def MAX_CALC(self):
        if self.count > 0:
            self.result = self.max
        yield

class VectorAccumulator:
    result = None
    
    def __init__(self, mode, size=3):
        self._mode = mode
        self._size = size
        self.axes = [NumberAccumulator(mode) for i in range(size)]
    
    def reset(self):
        for acc in self.axes:
            acc.reset()
        self.result = None
    
    def copy(self):
        return VectorAccumulator(self._mode, self._size)
    
    def __len__(self):
        return len(self.axes[0])
    
    def add(self, value):
        for i in range(len(self.axes)):
            self.axes[i].add(value[i])
    
    def calc(self):
        calcs = [axis.calc() for axis in self.axes]
        
        try:
            while True:
                for calc in calcs:
                    next(calc)
                yield
        except StopIteration:
            pass
        
        if len(self) > 0:
            self.result = [axis.result for axis in self.axes]
    
    def same(self, tolerance=1e-6):
        return [axis.same(tolerance) for axis in self.axes]

class AxisAngleAccumulator:
    result = None
    
    def __init__(self, mode):
        self._mode = mode
        self.x = NumberAccumulator(mode)
        self.y = NumberAccumulator(mode)
        self.z = NumberAccumulator(mode)
        self.a = NumberAccumulator(mode)
    
    def reset(self):
        self.x.reset()
        self.y.reset()
        self.z.reset()
        self.a.reset()
        self.result = None
    
    def copy(self):
        return AxisAngleAccumulator(self._mode)
    
    def __len__(self):
        return len(self.x)
    
    def add(self, value):
        self.x.add(value[0][0])
        self.y.add(value[0][1])
        self.z.add(value[0][2])
        self.a.add(value[1])
    
    def calc(self):
        calcs = (self.x.calc(),
                 self.y.calc(),
                 self.z.calc(),
                 self.a.calc())
        
        try:
            while True:
                for calc in calcs:
                    next(calc)
                yield
        except StopIteration:
            pass
        
        if len(self) > 0:
            self.result = ((self.x.result,
                            self.y.result,
                            self.z.result),
                            self.a.result)
    
    def same(self, tolerance=1e-6):
        return ((self.x.same(tolerance),
                 self.y.same(tolerance),
                 self.z.same(tolerance)),
                 self.a.same(tolerance))

class NormalAccumulator:
    # TODO !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    result = None
    
    def __init__(self, mode, size=3):
        self._mode = mode
        self._size = size
        self.axes = [NumberAccumulator(mode) for i in range(size)]
    
    def reset(self):
        for acc in self.axes:
            acc.reset()
        self.result = None
    
    def copy(self):
        return NormalAccumulator(self._mode, self._size)
    
    def __len__(self):
        return len(self.axes[0])
    
    def add(self, value):
        for i in range(len(self.axes)):
            self.axes[i].add(value[i])
    
    def calc(self):
        calcs = [axis.calc() for axis in self.axes]
        
        try:
            while True:
                for calc in calcs:
                    next(calc)
                yield
        except StopIteration:
            pass
        
        if len(self) > 0:
            self.result = [axis.result for axis in self.axes]
    
    def same(self, tolerance=1e-6):
        return [axis.same(tolerance) for axis in self.axes]

def accumulation_context(scene):
    obj = scene.objects.active
    if obj:
        obj_mode = obj.mode
    else:
        return 'OBJECT'
    
    if obj_mode == 'EDIT':
        obj_type = obj.type
        if obj_type in ('CURVE', 'SURFACE'):
            return 'CURVE'
        else:
            return obj_type
    elif obj_mode == 'POSE':
        return 'POSE'
    else:
        return 'OBJECT'
