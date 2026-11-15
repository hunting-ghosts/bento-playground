"""hooksig.py on a synthetic image: every tier, ambiguity, and the forbidden area.
No stock firmware needed: python3 tools/port/test_hooksig.py"""
import hashlib,json,random,struct,sys,tempfile,types,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import hooksig as H
B=H.BASE
def blob(seed,n):
 r=random.Random(seed);return bytes(r.choice(b'\x01\x02\x03\x04\x05\x06\x07\x09\x0a\x0b\x21\x22\x23\x31\x41\x51\x61\x71') for _ in range(n)) # never a pointer, BL or MOVW
class Image:
 """Named pieces at their offsets; a variant rebuilds with changed pieces."""
 def __init__(s):
  s.parts=[('a',blob(1,0x900)),('site1',bytes.fromhex('11223344')),('b',blob(2,0x700)),('site2',bytes.fromhex('55667788')),('c',blob(3,0x800)),
           ('f1',blob(11,0x80)),('f2',blob(12,0x80)),('f3',blob(13,0x80)),('f4',blob(14,0x80)),('f5',blob(15,0x80)),('d',blob(4,0x400)),('table',None),('e',blob(5,0x600)),('site3',bytes.fromhex('99aabbcc')),('g',blob(6,0x900))]
 def build(s,change=None):
  parts=[(n,(change or {}).get(n,d)) for n,d in s.parts];extra=(change or {}).get('+',{})
  out=bytearray();off={}
  for n,d in parts:
   out+=extra.get(n,b'')
   if n=='table':
    while len(out)%4:out+=b'\x00'
    off[n]=len(out);out+=b''.join(struct.pack('<I',B+off[f]|1) for f in ('f1','f2','f3','f4','f5'))
   else:
    if n.startswith('f'):
     while len(out)%4:out+=b'\x00'
    off[n]=len(out);out+=d
  return bytes(out),off
def make(img,off,tmp,sites):
 w=[dict(address=B+off[n]+rel,size=len(orig),original_hex=orig.hex(),replacement_hex=bytes(len(orig)).hex() if any(orig) else 'ff'*len(orig),reason=reason) for n,rel,orig,reason in sites]
 d=Path(tmp);(d/'stock.bin').write_bytes(img)
 (d/'FULL_MANIFEST.json').write_text(json.dumps(dict(label='T',sha256='0'*64,stock_sha256=hashlib.sha256(img).hexdigest(),writes=w)))
 (d/'features.json').write_text(json.dumps(dict(rules=[dict(match='^R6\\.13 ratchet',feature='ratchets',group='ratchets'),dict(match='table',feature='tables'),dict(match='.',feature='other')])))
 H.build(types.SimpleNamespace(stock=d/'stock.bin',build=d,out=d/'sites.json',md=None,features=d/'features.json'))
 return json.loads((d/'sites.json').read_text())
class Tiers(unittest.TestCase):
 def setUp(s):
  s.tmp=tempfile.mkdtemp();s.im=Image();s.img,s.off=s.im.build()
  s.doc=make(s.img,s.off,s.tmp,[('site1',0,bytes.fromhex('11223344'),'R6.13 ratchet hits'),('site2',0,bytes.fromhex('55667788'),'second'),('site3',0,bytes.fromhex('99aabbcc'),'third'),('table',8,struct.pack('<I',B+s.off['f3']|1),'table slot')])
 def loc(s,img):return {r['old']:r for r in H.locate(s.doc,img)}
 def key(s,n,rel=0):return '%08x'%(B+s.off[n]+rel)
 def test_inventory_fields_and_self_test(s):
  d=s.doc;s.assertEqual(d['selftest']['unique_exact_at_own_address'],4);by={x['address']:x for x in d['sites']}
  s.assertEqual((by[s.key('site1')]['feature'],by[s.key('site1')]['group']),('ratchets','ratchets'))
  s.assertEqual(by[s.key('table',8)]['kind'],'pointer slot');s.assertIn('pointer_signature',by[s.key('table',8)])
 def test_unchanged_surroundings_found_exactly_after_a_shift(s):
  img,off=s.im.build({'+':{'a':blob(90,0x40)}});r=s.loc(img)
  for n in ('site1','site2','site3'):
   x=r[s.key(n)];s.assertEqual((x['status'],x['tier'],x['guard'],x['confidence'],x['new']),('found-unique','exact','same-bytes','high','%08x'%(B+off[n])))
 def test_changed_site_bytes_are_found_by_context_and_flagged(s):
  img,off=s.im.build({'site2':bytes.fromhex('deadbeef')});x=s.loc(img)[s.key('site2')]
  s.assertEqual((x['status'],x['tier'],x['guard'],x['confidence'],x['new']),('found-unique','context','different-bytes','low','%08x'%(B+off['site2'])))
 def test_rewritten_code_after_the_site_leaves_the_context_before_it(s):
  img,off=s.im.build({'c':blob(77,0x800)});x=s.loc(img)[s.key('site2')]
  s.assertEqual((x['status'],x['new'],x['guard']),('found-unique','%08x'%(B+off['site2']),'same-bytes'));s.assertTrue(x['tier'].startswith('pre'))
 def test_a_second_copy_makes_the_site_ambiguous(s):
  o=s.off['site1'];copy=s.img[o-200:o+204];img=s.img+copy+blob(8,0x100);x=s.loc(img)[s.key('site1')]
  s.assertEqual((x['status'],x['new']),('ambiguous',None));s.assertEqual(len(x['candidates']),2)
 def test_a_copy_in_the_forbidden_area_is_not_a_candidate(s):
  o=s.off['site1'];copy=s.img[o-200:o+204];pad=0x080E0000-B-len(s.img)+0x100;img=s.img+bytes(pad)+copy+bytes(0x100);x=s.loc(img)[s.key('site1')]
  s.assertEqual((x['status'],x['new']),('found-unique',s.key('site1')))
 def test_pointer_slot_follows_its_relocated_functions(s):
  img,off=s.im.build({'+':{'f1':blob(91,0x24),'table':blob(92,0x10)},'d':blob(93,0x400),'e':blob(94,0x600)});x=s.loc(img)[s.key('table',8)]
  s.assertEqual((x['status'],x['tier'],x['new'],x['guard']),('found-unique','pointer','%08x'%(B+off['table']+8),'relocated-bytes'))
 def test_a_rewritten_site_is_missing_with_a_hint_from_its_surroundings(s):
  e=blob(5,0x600);g=blob(6,0x900)
  img,off=s.im.build({'site3':bytes.fromhex('01020304'),'e':e[:0x560]+blob(95,0xa0),'g':blob(96,0xa0)+g[0xa0:]});x=s.loc(img)[s.key('site3')]
  s.assertEqual((x['status'],x['new'],x['hint']),('missing',None,'%08x'%(B+off['site3'])))
 def test_inserted_bytes_at_a_rewritten_site_give_both_ends(s):
  e=blob(5,0x600);g=blob(6,0x900)
  img,off=s.im.build({'site3':bytes.fromhex('0102030405060708'),'e':e[:0x560]+blob(95,0xa0),'g':blob(96,0xa0)+g[0xa0:]});x=s.loc(img)[s.key('site3')]
  s.assertEqual((x['status'],x['tier'],x['candidates']),('ambiguous','landmark',['%08x'%(B+off['site3']),'%08x'%(B+off['site3']+4)]))
 def test_find_reports_areas(s):
  d=Path(s.tmp);doc=json.loads((d/'sites.json').read_text());doc['areas']=[dict(address='%08x'%(B+0x20),size=8,kind='stock-zero area',purpose='x')];(d/'sites.json').write_text(json.dumps(doc))
  H.find(types.SimpleNamespace(sites=d/'sites.json',stock=d/'stock.bin',out=d/'find.json',md=d/'find.md',match=None,overrides=None))
  out=json.loads((d/'find.json').read_text());s.assertEqual(out['areas'][0]['state'],'NOT zero in this image');s.assertIn('| found-unique | exact | high |',(d/'find.md').read_text())
if __name__=='__main__':unittest.main(verbosity=2)
