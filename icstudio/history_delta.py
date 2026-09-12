"""Reversible changes for validated JSON project trees.

History owns copied patch values. Applying a patch copies only edited ancestors;
it never mutates a previously published project or the patch itself. Arbitrary
editing callbacks still run on an isolated full working copy in model.History.
"""
from copy import deepcopy


def reverse(delta):
    if delta is None:return None
    kind=delta[0]
    if kind=='value':return (kind,delta[2],delta[1])
    if kind=='dict':return (kind,{k:reverse(v) for k,v in delta[1].items()},delta[3],delta[2])
    if kind=='list':return (kind,{k:reverse(v) for k,v in delta[1].items()})
    if kind=='splice':return (kind,delta[1],delta[3],delta[2])
    raise ValueError('Unknown history operation: '+str(kind))


def difference(before, after):
    if before is after:return None
    if isinstance(before,dict) and isinstance(after,dict):
        removed={k:deepcopy(v) for k,v in before.items() if k not in after}
        added={k:deepcopy(v) for k,v in after.items() if k not in before}
        changes={}
        for key in before.keys() & after.keys():
            delta=difference(before[key],after[key])
            if delta is not None:changes[key]=delta
        return ('dict',changes,removed,added) if changes or removed or added else None
    if isinstance(before,list) and isinstance(after,list):
        if len(before)==len(after):
            changes={}
            for i,(a,b) in enumerate(zip(before,after)):
                delta=difference(a,b)
                if delta is not None:changes[i]=delta
            return ('list',changes) if changes else None
        prefix=0;common=min(len(before),len(after))
        while prefix<common and difference(before[prefix],after[prefix]) is None:prefix+=1
        suffix=0
        while suffix<common-prefix and difference(before[-1-suffix],after[-1-suffix]) is None:suffix+=1
        return ('splice',prefix,deepcopy(before[prefix:len(before)-suffix]),deepcopy(after[prefix:len(after)-suffix]))
    if type(before) is type(after) and before==after:return None
    return ('value',deepcopy(before),deepcopy(after))


def apply(current, delta, forward=True):
    if delta is None:return current
    kind=delta[0]
    if kind=='value':return deepcopy(delta[2] if forward else delta[1])
    if kind=='dict':
        result=dict(current);_,changes,removed,added=delta
        drop,insert=(removed,added) if forward else (added,removed)
        for key in drop:del result[key]
        for key,value in insert.items():result[key]=deepcopy(value)
        for key,change in changes.items():result[key]=apply(current[key],change,forward)
        return result
    if kind=='list':
        result=list(current)
        for index,change in delta[1].items():result[index]=apply(current[index],change,forward)
        return result
    if kind=='splice':
        _,start,before,after=delta
        old,new=(before,after) if forward else (after,before)
        result=list(current);result[start:start+len(old)]=deepcopy(new);return result
    raise ValueError('Unknown history operation: '+str(kind))
