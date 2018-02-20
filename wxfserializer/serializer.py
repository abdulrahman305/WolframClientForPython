"""
"""
from wxfserializer.wxfutils import write_varint
from wxfserializer.wxfexpr import WXFConstants
from wxfserializer.wxfdataconsumer import InMemoryWXFDataConsumer
from wxfserializer.wxfexprprovider import WXFExprProvider

class SerializationContext:
    """ keeping track of the depth and the expected length of non-atomic elements. """
   
    __slots__ = '_depth', '_expected_length_stack', '_current_index_stack'

    def __init__(self):
        # first level has index 0 and lenght 1. It's the root of the expr
        # but does not represent anything in the final WL expr.
        self._depth = 0
        self._expected_length_stack = [1]
        # index starting at 0.
        self._current_index_stack = [0]
    
    def _checkInsert(self):
        if self._depth >= 0 and self._current_index_stack[self._depth] >= self._expected_length_stack[self._depth]:
            raise Exception('Out of bound.')

    def _stepOutFinalizedExpr(self):
        while self._depth >= 0 and self._current_index_stack[self._depth] == self._expected_length_stack[self._depth]:
            self._depth -= 1


    def addPart(self):
        self._checkInsert()
        self._current_index_stack[self._depth] += 1
        # This is the best place to output the context. Otherwise index values can be confusing.
        # print(repr(self))
        self._stepOutFinalizedExpr()

    def stepInNewExpr(self, length):
        # increment the index
        self.addPart()
        # go down one level in the expr tree, into the new expr.
        self._depth += 1
        # set or append element at index self._depth
        if len(self._expected_length_stack) <= self._depth:
            self._expected_length_stack.append(length)
        else:
            self._expected_length_stack[self._depth] = length

        if len(self._current_index_stack) <= self._depth:
            self._current_index_stack.append(0)
        else:
            self._current_index_stack[self._depth] = 0
        
        self._stepOutFinalizedExpr()

    def isValidFinalState(self):
        return self._depth == -1

    def __repr__(self):
        return 'SerializationContext(depth={}, element={}/{})'.format(self._depth, self._current_index_stack[self._depth], self._expected_length_stack[self._depth])
    

class WXFExprSerializer:
    """ Pulls instances of `WXFExpr` from an `WXFExprProvider`, serializes them into wxf bytes and appends the data to
    a `WXFDataConsumer`. Ensures the serialization state is consistent by update a `SerializationContext`.
    """
    __slots__ = '_expr_provider', '_data_consumer', '_context'

    def __init__(self, expr_provider, data_consumer):
        self._expr_provider = expr_provider
        self._data_consumer = data_consumer
        self._context = SerializationContext()
    
    @property
    def context(self):
        return self._context

    def serialize(self, pyExpr):
        for wxfExpr in self._expr_provider.pythonToWXFExpr(pyExpr):
            self._to_wxf_bytes(wxfExpr)
        if not self._context.isValidFinalState():
            raise Exception('Inconsistent state: truncated expr.')
        
    def _to_wxf_bytes(self, wxfExpr):
        self._data_consumer.append(wxfExpr.wxfType)
        if wxfExpr.wxfType == WXFConstants.String or wxfExpr.wxfType == WXFConstants.Symbol:
            self._context.addPart()
            write_varint(wxfExpr.length, self._data_consumer)
            self._data_consumer.extend(wxfExpr.value)
        elif wxfExpr.wxfType == WXFConstants.Integer8 or wxfExpr.wxfType == WXFConstants.Integer16 or wxfExpr.wxfType == WXFConstants.Integer32 or wxfExpr.wxfType == WXFConstants.Integer64:
            self._context.addPart()
            self._data_consumer.extend(
                wxfExpr.value.to_bytes(wxfExpr.intSize, byteorder='little', signed=True)
            )
        elif wxfExpr.wxfType == WXFConstants.Function:
            self._context.stepInNewExpr(wxfExpr.length + 1)
            write_varint(wxfExpr.length, self._data_consumer)
        elif wxfExpr.wxfType == WXFConstants.PackedArray or wxfExpr.wxfType == WXFConstants.RawArray:
            self._context.addPart()
            self._data_consumer.append(wxfExpr.value_type)
            write_varint(wxfExpr.rank, self._data_consumer)
            for dim in wxfExpr.dimensions:
                write_varint(dim, self._data_consumer)
            if wxfExpr.data is not None:
                self._data_consumer.extend(wxfExpr.data)
            else:
                raise Exception("Missing array data.")
        else:
            raise TypeError
