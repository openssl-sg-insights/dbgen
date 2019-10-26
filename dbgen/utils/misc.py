from typing  import Any, Dict as D, Type, TypeVar, Union as U, List as L
from abc     import ABCMeta, abstractmethod
from copy    import deepcopy
from string  import ascii_lowercase
from importlib import import_module
from inspect import getfullargspec

from hypothesis import infer # type: ignore
from hypothesis.strategies import (SearchStrategy, one_of, booleans, # type: ignore
                                   integers, just, text, builds, none, floats,
                                   dictionaries, lists, recursive)

from json import loads, dumps

from dbgen.utils.str_utils import hash_

NoneType = type(None)

##############################################################################

T = TypeVar('T')

def identity(x : T) -> T:
    return x

def kwargs(x: Any) -> L[str]:
    return sorted(getfullargspec(type(x))[0][1:])

anystrat = one_of(text(), booleans(), text(), integers(), none())
nonempty = text(min_size=1)
letters  = text(min_size=1,alphabet=ascii_lowercase)

def build(typ:Type) -> SearchStrategy:
    """Unfortunately, hypothesis cannot automatically ignore default kwargs."""
    args,_,_,_,_,_,annotations = getfullargspec(typ)
    # use default kwarg value if type is Any
    kwargs = {k:infer for k in args[1:] if annotations[k]!=Any}
    return builds(typ, **kwargs)

simple = ['int','str','float','NoneType','bool']
complex = ['tuple','list','set','dict']

def to_dict(x: Any, id_only: bool = False) -> U[L, int, float, str, D[str, Any], NoneType]:
    '''Create JSON serializable structure for arbitrary Python/DbGen type.'''
    module, ptype = type(x).__module__, type(x).__name__
    metadata = dict(_pytype=module+'.'+ptype) # type: D[str, Any]
    if module == 'builtins' and ptype in simple:
        return x
    elif module == 'builtins' and ptype in complex:
        if ptype == 'dict':
            assert all([isinstance(k,str) for k in x.keys()]), x
            return {k:to_dict(v, id_only) for k,v in x.items()}
        elif ptype == 'list':
            return [to_dict(xx, id_only) for xx in x] # type: ignore
        elif ptype in ['tuple','set']:
            return dict(**metadata, _value=[to_dict(xx, id_only) for xx in x])
        else:
            raise TypeError(x)
    else:
        assert hasattr(x,'__dict__'), metadata
        data = {k:to_dict(v, id_only) for k,v in sorted(vars(x).items()) if
                (k in kwargs(x)) or (not id_only and k[0]!='_')}
        #if ' at 0x' in str(v):  raise ValueError('serializing an object with reference to memory:'+ str(vars(self)))
        if not id_only:
            hashdict = {**metadata,**{k:to_dict(data[k],id_only=True)
                                      for k in sorted(kwargs(x))}}
            metadata['_uid'] = hash_(dumps(hashdict,indent=4,sort_keys=True))
        return {**metadata,**data}

def from_dict(x:Any) -> Any:
    '''Create a python/DbGen type from a JSON serializable structure.'''
    if isinstance(x,dict):
        ptype = x.get('_pytype', '')
        if 'dbgen' in ptype:
            mod, cname = '.'.join(ptype.split('.')[:-1]), ptype.split('.')[-1]
            constructor = getattr(import_module(mod), cname)
            return constructor(**{k:from_dict(v) for k,v in x.items()
                                 if k in getfullargspec(constructor)[0][1:]})
        elif 'builtins/tuple' == ptype:
            return tuple([from_dict(xx) for xx in x]) # data-level tuple
        elif 'builtins/set' == ptype:
            return set([from_dict(xx) for xx in x]) # data-level tuple
        else:
            assert '_ptype' not in x
            return {k:from_dict(v) for k,v in x.items()} # data-level dict
    elif isinstance(x,(int,float,list,type(None),str)):
        if isinstance(x, list): return [from_dict(xx) for xx in x]
        else:                   return x
    else:
        raise TypeError(x)

class Base(object,metaclass=ABCMeta):
    '''Common methods shared by many DbGen objects.'''

    def __init__(self) -> None:
        fields = set(vars(self))
        args = set(kwargs(self))
        missing = args - fields
        assert not missing, 'Need to store args {} of {}'.format(missing, self)
        assert not any([a[0]=='_' for a in args]), args

    @abstractmethod
    def __str__(self)->str:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def strat(cls) -> SearchStrategy:
        """A hypothesis strategy for generating random examples."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return str(self)

    def __eq__(self, other : Any) -> bool:
        '''
        Maybe the below should be preferred? Try it out, sometime!
        return type(self) == type(other) and vars(self) == vars(other)
        '''
        if type(other) == type(self):
            return vars(self) == vars(other)
        else:
            args = [self, type(self), other, type(other)]
            err = 'Equality type error \n{} \n({}) \n\n{} \n({})'
            raise ValueError(err.format(*args))

    def copy(self : T) -> T:
        return deepcopy(self)

    def toJSON(self) -> str:
        return dumps(to_dict(self),indent=4,sort_keys=True)

    @staticmethod
    def fromJSON(s : str) -> 'Base':
        val = from_dict(loads(s))
        if not isinstance(val,Base):
            import pdb;pdb.set_trace()
        assert isinstance(val,Base)
        return val

    def __hash__(self)->int:
        return self.hash

    @property
    def hash(self) -> int:
        dic = to_dict(self)
        assert isinstance(dic, dict)
        return dic['_uid']


if __name__ == '__main__':
    from dbgen import Obj, Rel, Attr, Int
    obj = Obj('Table1', attrs=[Attr('mike',Int('big'))], fks=[Rel('sample')])
    print(dumps(to_dict(obj,id_only=True),indent=4,sort_keys=True))
    print(obj.toJSON())
    print(obj.hash)
