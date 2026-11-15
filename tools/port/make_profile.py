"""Draft a version profile (JSON) from the generated inventory and match results.

The draft is NOT a build input until every entry with review=true has been
checked and every unresolved entry has a manual override with a reason.
"""
import argparse,json,hashlib,collections,pickle
from pathlib import Path
AUTO={'high','exact','exact-majority','bracketed'}         # accepted by evidence
REVIEW={'medium','low-aligned','fuzzy-equal','base+offset','low'}
def main():
 p=argparse.ArgumentParser()
 for k in ('inventory','match','offsets','keymap','old','new','controller','out'):p.add_argument('--'+k,type=Path,required=k!='controller')
 p.add_argument('--imm-tab',type=Path);a=p.parse_args()
 inv=json.loads(a.inventory.read_text());mt=json.loads(a.match.read_text());off=json.loads(a.offsets.read_text())['constants'];km=json.loads(a.keymap.read_text())
 new=a.new.read_bytes()
 prof=dict(profile_schema=2,firmware_version='1.6.8',status='DRAFT - generated, not a build input',
  main=dict(sha256=hashlib.sha256(new).hexdigest(),size=len(new),end=hex(0x08040000+len(new))),
  controller_sha256=hashlib.sha256(a.controller.read_bytes()).hexdigest() if a.controller else None,
  derived_from=dict(stock='1.6.1',stock_sha256=inv['stock_sha256'],playground=inv['label'],playground_sha256=inv['sha256']))
 fm={};c=collections.Counter()
 for k,e in mt['flash'].items():
  st='auto' if e['conf'] in AUTO else ('review' if e['conf'] in REVIEW and e.get('new') else 'unresolved')
  c['flash_'+st]+=1
  fm[k]=dict(new=e.get('new'),conf=e['conf'],status=st,how=e.get('how'),used_by=(e.get('source') or e.get('sites'))[:3])
 rm={}
 for k,e in mt['ram'].items():
  st='auto' if e['conf'] in AUTO else ('review' if e['conf'] in REVIEW and e.get('new') else 'unresolved')
  c['ram_'+st]+=1;rm[k]=dict(new=e.get('new'),conf=e['conf'],status=st,how=e.get('how'),used_by=(e.get('source') or e.get('sites'))[:3])
 hooks=[]
 for x in mt['patches']:
  ok=x['guard'] in ('same-bytes','relocated-bytes') and x['match']['conf'] in AUTO
  st='auto' if ok else ('review' if x['guard'] in ('same-bytes','relocated-bytes') else 'unresolved')
  c['patch_'+st]+=1
  hooks.append(dict(old=x['address'],size=x['size'],new=x['match'].get('new'),conf=x['match']['conf'],guard=x['guard'],new_original_hex=x.get('new_original_hex'),status=st,reason=x['reason']))
 consts={k:dict(verdict=v['verdict'],evidence=v['evidence'],split_evidence=v.get('split_evidence'),new_values=v.get('split_new_values'),examples=v['changed_examples'][:2],used_by=v['source'][:3]) for k,v in off.items() if v['verdict'] in ('changed','mixed','unverified','split-changed','split-mixed')}
 prof.update(counts=c,hooks=hooks,flash=fm,ram=rm,param_keys=dict(method='alignment of the 271/270 native registrations (registry add 08163952 -> 081657F2)',
  rule='keys 0x02..0x138 unchanged; 0x139..0x13B (In 1/In 2/In 3) became one key 0x139 Input Gain; 0x13C..0x1D8 -> key-2; 0x1D9.. -> key-1; new 0x1D7 LastDate',map=km['keys'],changes=km['changes']),
  ui_ids=dict(method='immediate evidence at matched native sites',rule='<=0x1011 unchanged; 0x1013..0x1039 +2; 0x103E..0x1046 +3; 0x1012, 0x103A..0x103D and >0x1046 unproven'),
  constants_needing_review=consts)
 a.out.write_text(json.dumps(prof,indent=1)+'\n');print(dict(c))
if __name__=='__main__':main()
