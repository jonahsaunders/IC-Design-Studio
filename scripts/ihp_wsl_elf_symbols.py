"""Bounded static ELF64/x86-64 dynamic-symbol inspection; never loads a module."""
import struct
from pathlib import Path

def elf_symbols(path):
 if not 64<=Path(path).stat().st_size<=256*1024*1024:raise ValueError('ELF input size outside static inspection bound')
 data=Path(path).read_bytes()
 def need(ok,message):
  if not ok:raise ValueError(message)
 need(len(data)>=64 and data[:7]==b'\x7fELF\x02\x01\x01','Expected little-endian ELF64')
 need(struct.unpack_from('<H',data,18)[0]==62,'Expected x86-64 ELF')
 offset=struct.unpack_from('<Q',data,40)[0];size,count=struct.unpack_from('<HH',data,58)
 need(size==64 and 0<count<=65535 and offset+count*size<=len(data),'Bounded section table')
 sections=[struct.unpack_from('<IIQQQQIIQQ',data,offset+i*size) for i in range(count)]
 def contents(index):
  need(0<=index<count,'Section index');s=sections[index]
  need(s[4]+s[5]<=len(data),'Section bounds');return data[s[4]:s[4]+s[5]]
 def name(strings,index):
  need(0<=index<len(strings),'String offset');end=strings.find(b'\0',index);need(end>=index,'Unterminated ELF string')
  return strings[index:end].decode('ascii')
 needed=[];undefined={};weak=[];exports={};dynamic_tables=0;symbol_tables=0
 for index,s in enumerate(sections):
  if s[1] not in (6,11):continue
  strings=contents(s[6]);table=contents(index)
  if s[1]==6:
   dynamic_tables+=1;need(s[9]==16 and len(table)%16==0,'Dynamic table size')
   for pos in range(0,len(table),16):
    tag,value=struct.unpack_from('<qQ',table,pos)
    if tag==0:break
    if tag==1:needed.append(name(strings,value))
  else:
   symbol_tables+=1;need(s[9]==24 and len(table)%24==0,'Symbol table size')
   for pos in range(0,len(table),24):
    n,info,visibility,section,value,length=struct.unpack_from('<IBBHQQ',table,pos)
    if not n:continue
    symbol=name(strings,n);binding=info>>4;kind=info&15
    if section==0:
     if binding==2:weak.append(symbol)
     elif binding==1:undefined[symbol]=kind
    elif binding in (1,2,10) and visibility&3 in (0,3):exports[symbol]=kind
 need(dynamic_tables==symbol_tables==1,'One dynamic and symbol table required')
 return dict(needed=needed,undefined=undefined,weak_undefined=sorted(weak),exports=exports)

def resolve_symbols(module,scope):
 unresolved={name:kind for name,kind in module['undefined'].items() if name not in scope or not (kind==0 or scope[name]==0 or kind==scope[name] or {kind,scope[name]}<={2,10})}
 if unresolved:raise ValueError('Undefined strong symbols outside reviewed engine scope: '+repr(unresolved))
 return {'strong_undefined_count':len(module['undefined']),'weak_undefined':module['weak_undefined'],'needed':module['needed'],'scope':'STATIC_ENGINE_AND_AUTHENTICATED_DEPENDENCY_EXPORT_JOIN_NOT_SELF_CONTAINED'}
