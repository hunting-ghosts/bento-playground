"""Definitive parameter-key map from two emulator registry dumps (read-only).

The dumps come from running each image's own registry builder in the emulator
fixtures (key -> name, type for every descriptor). Descriptors are aligned in
key order by (name, type); the result is checked against the rule derived from
the static registration alignment (keys.py).
"""
import json,sys,difflib,collections
def rule(k):return k if k<0x139 else 0x139 if k<0x13c else k-2 if k<0x1d9 else k-1
a=json.load(open(sys.argv[1]));b=json.load(open(sys.argv[2]))
A=sorted((int(k,16),v['name'],v['type']) for k,v in a.items());Bn=sorted((int(k,16),v['name'],v['type']) for k,v in b.items())
sm=difflib.SequenceMatcher(None,[(x[1],x[2]) for x in A],[(x[1],x[2]) for x in Bn],autojunk=False)
km={};changes=[]
for tag,i1,i2,j1,j2 in sm.get_opcodes():
 if tag=='equal':
  for x,y in zip(A[i1:i2],Bn[j1:j2]):km[x[0]]=y[0]
 else:changes.append(dict(tag=tag,old=[(hex(x[0]),x[1]) for x in A[i1:i2]],new=[(hex(y[0]),y[1]) for y in Bn[j1:j2]]))
dis=[(hex(k),hex(v),hex(rule(k))) for k,v in sorted(km.items()) if v!=rule(k)]
json.dump(dict(map={hex(k):hex(v) for k,v in sorted(km.items())},changes=changes,rule_disagreements=dis),open(sys.argv[3],'w'),indent=1)
print('%d/%d keys aligned; rule disagreements %d %s'%(len(km),len(A),len(dis),dis[:12]))
for c in changes:print(' ',c['tag'],c['old'],'->',c['new'])
