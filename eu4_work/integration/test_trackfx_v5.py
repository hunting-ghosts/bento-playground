"""Run 17 (owner, 13 Nov): Track FX v5 and the saturator on the 1.6.8 build (emulator, software evidence only).
B: Left/Right select the sections through the native button dispatch, no EQ/Comp/Clip footer toggles, footer view
   toggles "Tracks | Track FX" on both pages (taps navigate), section On/Off and Auto Makeup as switch A, the painted
   picture (track colour, native-size scales, no value text under the graphs, knee exactly at Threshold, saturator
   waveform per Mode/Drive/Level, frame on the selected section).
C: the saturator through the real native mixer and the M7 Track FX adapter: an old project's ceiling loads as the
   identical sound (golden digests recorded on the run-16 DSP: build p168_b02 = run 16 + item A, mailbox value 17 =
   ceiling -c dB), Hard clamps, Level, automatic compensation, the packed mailbox word, save/load (bento_fx_version 3)
   and old versions 1/2. On 1.6.1 (no saturator; chord editor built in) Unchanged161 asserts the previous Track FX."""
import sys as _s,pathlib as _p;_s.path.insert(0,str(next(p for p in _p.Path(__file__).resolve().parents if (p/'eu4_work/integration/native_ids.py').exists())/'eu4_work/integration'));import native_ids as N # 1.6.8 port: version-dependent native offsets
import gc,hashlib,struct,unittest
import numpy as np
from unicorn import UC_HOOK_CODE
from test_integration import Fixture,UU,KEYS,DEFAULT
KEEP=[]
MODE,LEVEL=0x128,0x129
def pack(on=1,hard=0,level=0):return (on&1)|(hard&1)<<1|(level&255)<<8
def clip_audio(p,word,v17,blocks=40,seed=5):
    """Mailbox scenario exactly as the M7 sees it: track 2, value 16 = word, 17 = v17, noise peaking near 1."""
    p.mixer();s=list(DEFAULT);s[16]=word;s[17]=v17;p.mailbox({2:s})
    rng=np.random.default_rng(seed);h=hashlib.sha256();out=[]
    for b in range(blocks):
        x=(rng.standard_normal(128)*.6).astype('float32');y=p.audio(2,x,None);h.update(y.tobytes());out.append(y)
    return h.hexdigest(),np.concatenate(out)
def settled(p,word,v17,x):
    p.mixer();s=list(DEFAULT);s[16]=word;s[17]=v17;p.mailbox({2:s})
    for _ in range(120):y=p.audio(2,x,None)
    return y
GOLDEN={1:'4c7f3fee61ca93762b3c1370c64383b90e7dd8db58bcfd49e294117e135997c8',3:'f98704c1c73e1addce0f8859ea312ae2333f2449c604809d83c8165a05a4c9ec',
        6:'0a59cb2a1b27b69b61f50e9a1ef98006754bebeebaaee6c709c604d5ff9118be',12:'fa527898b1d1a98efb0884f269f29ff2b4c4da90f4d06866bec6f551eddb787a'}
def fixture():p=Fixture();KEEP.append(p);return p
class Saturator(unittest.TestCase):
    def setUp(self):
        if not N.FW168:self.skipTest('1.6.8 saturator (1.6.1: Unchanged161)')
    def test_old_ceiling_loads_as_drive_with_the_identical_sound(self):
        for c,want in GOLDEN.items():self.assertEqual(clip_audio(fixture(),1,c)[0],want,c) # Drive c dB = old ceiling -c dB, Soft, 0 dB
    def test_hard_clamps_at_the_clip_level_and_soft_rounds_below_it(self):
        # the Track FX hook sits after the native input gain (fixture track level: +1 dB), so the curve sees x*g
        x=np.full(128,.9,dtype='float32');k=10**(-6/20)
        hard=settled(fixture(),pack(1,1),6,x);soft=settled(fixture(),pack(1,0),6,x)
        self.assertAlmostEqual(float(hard.max()),k,places=5);self.assertLess(float(soft.max()),.99*k)
        _,y=clip_audio(fixture(),pack(1,1),6,blocks=120);self.assertLessEqual(float(np.abs(y[80*128:]).max()),k+1e-6) # after the 20 ms fade-in has settled
        self.assertGreater(float(np.abs(y[80*128:]).max()),k-1e-6)
    def test_level_scales_after_the_curve(self):
        x=np.full(128,.5,dtype='float32');ref=float(settled(fixture(),pack(1,1,0),0,x)[-1]) # Hard at Drive 0: unclipped (0.56 < 1)
        for level in (-12,-6,6):
            y=settled(fixture(),pack(1,1,level),0,x);self.assertAlmostEqual(float(y[-1]),ref*10**(level/20),places=5,msg=level)
    def test_compensation_keeps_quiet_signals_at_unity(self):
        x=(np.sin(np.arange(128)*2*np.pi*750/48000)*.01).astype('float32')
        dry=np.abs(settled(fixture(),0,1,x)).max() # same native path with the saturator off
        for drive in (0,12,24):
            y=settled(fixture(),pack(1,0),drive,x);self.assertAlmostEqual(20*np.log10(np.abs(y).max()/dry),0,delta=.25,msg=drive)
    def test_disabled_saturator_with_mode_and_level_stays_bypassed(self):
        _,y=clip_audio(fixture(),pack(0,1,-12),24);_,z=clip_audio(fixture(),0,1);self.assertEqual(y.tobytes(),z.tobytes())
    def test_invalid_packed_words_are_rejected_by_the_m7(self):
        p=fixture();p.mixer();x=np.full(128,.2,dtype='float32');p.audio(0,x,DEFAULT);serial=p.r(0x240416c4)
        for word,v17 in ((pack(1,0,13),1),(pack(1)|4,1),(1<<16|1,1),(pack(1),25),(pack(1),-1)):
            s=list(DEFAULT);s[16]=word;s[17]=v17;p.mailbox({0:s});p.audio(0,x,None);self.assertEqual(p.r(0x240416c4),serial,(hex(word),v17))
    def test_ui_events_pack_mode_and_level_into_the_mailbox(self):
        p=fixture();p.direct_open()
        for key,v in ((KEYS[16],1),(MODE,1),(LEVEL,-5),(KEYS[17],9)):p.event(key,v)
        self.assertEqual([p.value(k) for k in (KEYS[16],MODE,KEYS[17],LEVEL)],[1,1,9,-5])
        self.assertEqual(struct.unpack('<2i',p.u.mem_read(0x24041468+64,8)),(pack(1,1,-5),9)) # track 1 values 16/17
        p.event(LEVEL,40);p.event(KEYS[17],-3);p.event(MODE,5);self.assertEqual([p.value(k) for k in (LEVEL,KEYS[17],MODE)],[12,0,1]) # native clamps
        p.event(KEYS[16],0);self.assertEqual([p.value(k) for k in (KEYS[16],MODE,LEVEL)],[0,1,12]) # Off keeps Mode/Level
    def test_saturator_bank_registry_and_title(self):
        p=fixture();p.registry();r=0x20020000
        for k in (MODE,LEVEL):self.assertEqual(struct.unpack('<H',p.u.mem_read(r+k*32,2))[0],0,hex(k)) # empty after native registry construction
        self.assertFalse(N.CHORD_EDITOR) # their only other owner (the progression editor) is switched off in this build
        v=p.direct_open();p.u.mem_write(0x30024b00+0x12c,b'\x1a') # the fixture logs the navigation; the page is Track FX now
        for _ in range(2):p.call(UU['fx_dispatch'],0x30024b00,0xaf,0,9);p.call(UU['fx_dispatch'],0x30024b00,0xb0,0,9)
        p.w(0x20016000,42);p.call(0x08145efc,v,0x20016000);self.assertEqual([struct.unpack('<H',p.u.mem_read(v+0x93c4+0x14+i*2,2))[0] for i in range(8)],[KEYS[16],MODE,KEYS[17],LEVEL,0,0,0,KEYS[18]])
        self.assertEqual(p.text(p.r(v+0x93c8)),'Track 1 / Saturator')
        d=r+MODE*32;self.assertEqual(p.u.mem_read(d+2,1)[0],7);self.assertEqual(p.r(d+12),2);names=p.r(d+8)
        self.assertEqual([p.text(p.r(names+4*i)) for i in range(2)],['Soft','Hard'])
        for k,lo,hi,name in ((KEYS[17],0,24,'Drive'),(LEVEL,-12,12,'Level'),(KEYS[16],0,1,'Saturator')):
            d=r+k*32;self.assertEqual(struct.unpack('<2i',p.u.mem_read(d+16,8)),(lo,hi));self.assertEqual(p.text(p.r(d+4)),name)
    def save(self,p):
        p.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:p.ret(14),begin=0x08133f7c,end=0x08133f7c)
        obj=0x20010000;p.w(obj+16,100);p.u.mem_write(obj+4,b'\x0e');p.call(UU['fx_save'],obj,0x20017000);return dict(p.attrs)
    def load(self,attrs):
        q=fixture();q.registry();q.attrs=dict(attrs);obj=0x20010000;q.w(obj+16,100);q.u.mem_write(obj+4,b'\x0e');q.call(UU['fx_load'],0x20011000,obj)
        q.u.hook_add(UC_HOOK_CODE,lambda u,a,n,d:q.ret(14),begin=0x08133f7c,end=0x08133f7c)
        ev=0x20012000;q.w(ev,0x3f);q.call(UU['fx_finish'],0,ev);q.direct_open();return q
    def test_save_version_3_keeps_the_ceiling_attribute_and_loads_back(self):
        p=fixture();p.direct_open()
        for key,v in ((KEYS[16],1),(MODE,1),(LEVEL,-5),(KEYS[17],9)):p.event(key,v)
        a=self.save(p);self.assertEqual(a['bento_fx_version'],3)
        self.assertEqual([a['bento_fx_v1_%02d'%i] for i in (16,17,19,20)],[1,(-9)&0xffffffff,1,(-5)&0xffffffff]) # 17 = ceiling (-Drive)
        self.assertNotIn('bento_fx_v1_18',a)
        q=self.load(a);self.assertEqual([q.value(k) for k in (KEYS[16],MODE,KEYS[17],LEVEL)],[1,1,9,-5])
    def test_old_versions_load_their_ceiling_as_drive(self):
        for ver,c in ((2,-4),(1,-12),(2,0)):
            p=fixture();p.direct_open();p.event(KEYS[16],1);a=self.save(p);a['bento_fx_version']=ver;a['bento_fx_v1_17']=c&0xffffffff
            for i in (19,20):a.pop('bento_fx_v1_%02d'%i)
            q=self.load(a);self.assertEqual([q.value(k) for k in (KEYS[16],MODE,KEYS[17],LEVEL)],[1,0,-c,0],(ver,c))
            q.mixer();self.assertEqual(struct.unpack('<2i',q.u.mem_read(0x24041468+64,8)),(1,-c)) # the M7 gets the identical word
    def test_missing_track_fx_data_gives_drive_1_soft_0_db(self):
        q=self.load({});self.assertEqual([q.value(k) for k in (KEYS[16],MODE,KEYS[17],LEVEL)],[0,0,1,0])

class TrackFxView(unittest.TestCase):
    """B: the page through the Perform fixture (real native GenericProperties view, header apply, fonts, painter)."""
    def setUp(self):
        if not N.FW168:self.skipTest('1.6.8 Track FX v5 (1.6.1: Unchanged161)')
    def page(self,track=0,values=(),section=0):
        from test_perform_ui import Perform,VIEW,POINT,MODEL
        import render
        p=Perform();KEEP.append(p);p.open_track_fx()
        def ev(key,v):p.u.mem_write(POINT,struct.pack('<5I',0xcf,0,key,v&0xffffffff,0));p.call('fx_event',VIEW,POINT)
        if track:ev(KEYS[18],track+1)
        for key,v in values:ev(key,v)
        for _ in range(section):p.call('fx_dispatch',MODEL,0xaf,0,9);p.call('fx_dispatch',MODEL,0xb0,0,9)
        p.call('fx_header',MODEL,0,VIEW+0x93c4,0,0x08145f22);p.fx_values()
        render.clear(p.e,0xf1);p.labels.clear();p.fills.clear()
        p.u.mem_write(render.CTX,struct.pack('<II',1,render.SURF));p.call('pg_bar_paint',p.bar(),render.CTX)
        p.ui=render.ui(p.e);return p
    def keys(self,p):
        from test_perform_ui import VIEW
        return [p.e.h(VIEW+0x93c4+0x14+i*2) for i in range(8)]
    def test_left_right_select_sections_through_the_native_button_dispatch(self):
        from test_perform_ui import MODEL
        p=self.page();self.assertEqual(self.keys(p),KEYS[:8])
        for index,want in ((9,KEYS[8:16]),(9,[KEYS[16],MODE,KEYS[17],LEVEL,0,0,0,KEYS[18]]),(9,None),(0,KEYS[8:16]),(0,KEYS[:8]),(0,KEYS[:8])):
            self.assertEqual(p.call('fx_dispatch',MODEL,0xaf,0,index),1);self.assertEqual(p.call('fx_dispatch',MODEL,0xb0,0,index),1) # press and release consumed
            p.call('fx_header',MODEL,0,0x0+__import__('test_perform_ui').VIEW+0x93c4,0,0x08145f22)
            if want:self.assertEqual(self.keys(p),want)
            else:self.assertEqual(self.keys(p)[0],KEYS[16]) # no wrap past the Saturator
    def footer(self,p):
        from test_perform_ui import POINT
        import render
        out=POINT+0x400;p.u.mem_write(out,render.tpl(p.e,20));p.call('device_header_prepare',out)
        return [(p.e.h(out+N.HDR(0x74)+i*48+44),p.e.text(out+N.HDR(0x74)+i*48),p.u.mem_read(out+N.HDR(0x74)+i*48+0x21,1)[0]) for i in range(6)]
    def test_footer_view_toggles_replace_the_section_toggles_and_navigate(self):
        from test_perform_ui import VIEW,POINT,MODEL
        p=self.page();f=self.footer(p)
        self.assertEqual(f[4:],[(0x1078 if False else 0x1077,'Tracks',0),(0x1078,'Track FX',1)][:2] and [(0x1077,'Tracks',0),(0x1078,'Track FX',1)])
        self.assertEqual([x[0] for x in f[:4]],[0,0,0,0]);self.assertNotIn(0x1079,[x[0] for x in f]) # no EQ/Compressor/Saturator toggles
        p.u.mem_write(POINT,struct.pack('<5I',0x1077,0,0,0,0));self.assertEqual(p.call('fx_event',VIEW,POINT),1);self.assertEqual(p.navs[-1],2) # Tracks
        p.call('fx_nav',MODEL,2);self.assertEqual(p.call('fx_screen_active'),0)
        f=self.footer(p);self.assertEqual(f[4:],[(0x1077,'Tracks',1),(0x1078,'Track FX',0)]) # the Tracks page shows the same toggles
        from test_tracks import VIEW as TV
        p.u.mem_write(POINT,struct.pack('<5I',0x1078,0,0,0,0));p.call('pg_tracks_event',TV,POINT)
        self.assertEqual(p.navs[-1],0x1a);self.assertEqual(p.call('fx_screen_active'),1) # Track FX opened from the footer
    def test_picture_has_scales_and_no_value_text_under_the_graphs(self):
        p=self.page(values=[(KEYS[0],1),(KEYS[8],1),(KEYS[16],1)])
        texts=[t for t,_ in p.labels]
        for t in ('EQ','Compressor','Saturator','+12','0','-12','100','1k','10k','-60','0 dB','GR'):self.assertIn(t,texts)
        for t in ('LOW SHELF','MID PEAK','HIGH SHELF','Threshold','Ratio','Ceiling','ON','OFF','On','Off','120 Hz','Soft Clip','Unavailable','GR (dB)'):self.assertNotIn(t,texts)
        self.assertTrue(all(f==0 for _,f in p.labels)) # native 24 px text only
    def colour(self,p,track):return p.call(0x08140ebc,track)
    def test_graphs_use_the_selected_tracks_colour(self):
        for track in (0,6):
            p=self.page(track=track,values=[(KEYS[0],1),(KEYS[2],60)]);c=self.colour(p,track)
            self.assertGreater(sum(1 for _,col in p.fills if col==c),500,track) # curves are drawn in the track colour
            others=self.colour(p,3 if track!=3 else 4);self.assertEqual(sum(1 for _,col in p.fills if col==others),0)
    def pix(self,p,x,top):return int(p.ui[top,x])
    def test_compressor_knee_is_exactly_at_threshold_and_slope_follows_ratio(self):
        for thr,ratio in ((-18,3),(-40,8),(-6,2)):
            p=self.page(values=[(KEYS[8],1),(KEYS[9],thr),(KEYS[10],ratio)]);c=self.colour(p,0)
            X=lambda db:660+(db+60)*220//60;Y=lambda db:132+248-(db+60)*248//60
            self.assertEqual(self.pix(p,X(thr),Y(thr)),c,(thr,ratio))            # the knee pixel
            end=thr+(0-thr)//ratio;self.assertEqual(self.pix(p,880,Y(end)),c)   # 0 dB in -> Threshold + (0-Threshold)/Ratio out
            self.assertNotEqual(self.pix(p,880,Y(0)),c)                         # not the 1:1 line above the knee
            self.assertEqual(self.pix(p,X(-60),Y(-60)),c)                       # 1:1 below the knee
    def sat_box(self,p):return p.ui[132:381,968:1263].copy()
    def test_saturator_picture_follows_mode_drive_and_level(self):
        base=[(KEYS[16],1)]
        a=self.sat_box(self.page(values=base+[(KEYS[17],10),(MODE,0)]));b=self.sat_box(self.page(values=base+[(KEYS[17],10),(MODE,1)]))
        c=self.sat_box(self.page(values=base+[(KEYS[17],3),(MODE,0)]));d=self.sat_box(self.page(values=base+[(KEYS[17],10),(MODE,0),(LEVEL,-6)]))
        for x,y in ((a,b),(a,c),(a,d)):self.assertFalse(np.array_equal(x,y))
        p=self.page(values=base+[(KEYS[17],12),(MODE,1)]);col=self.colour(p,0);box=self.sat_box(p)
        rows=[r for r in range(box.shape[0]) if (box[r]==col).any()];amp=248//2-8;mid=248//2
        k=10**(-12/20);self.assertAlmostEqual((mid-rows[0])/amp,k,delta=.03) # Hard: flat at the clip level 10^(-Drive/20)
        flat=sum(1 for x in range(box.shape[1]) if box[rows[0],x]==col or box[rows[0]+1,x]==col);self.assertGreater(flat,60)
    def test_frame_follows_the_selected_section(self):
        for section,(x0,x1) in enumerate(((4,628),(636,936),(944,1275))):
            p=self.page(section=section)
            for other,(a,b) in enumerate(((4,628),(636,936),(944,1275))):
                self.assertEqual(self.pix(p,(a+b)//2,76)==0xa6,other==section,(section,other))
    def test_section_switches_are_style_a_without_text(self):
        p=self.page(values=[(KEYS[8],1)],section=1);texts=[t for t,_ in p.labels]
        for t in ('Compressor','Thresh dB','Auto Makeup'):self.assertIn(t,texts)
        self.assertNotIn('On',texts);self.assertNotIn('Off',texts)
        self.assertEqual(self.pix(p,58+33,40+10),0xf2);self.assertEqual(self.pix(p,58+11,40+10),0xf1) # encoder 1 switch On: white knob on the right, none on the left
class Unchanged161(unittest.TestCase):
    def setUp(self):
        if N.FW168:self.skipTest('1.6.1 keeps the previous clipper')
    def test_previous_soft_clip_bank_and_no_saturator_keys(self):
        p=fixture();v=p.direct_open();p.u.mem_write(0x30024b00+0x12c,b'\x1a') # the fixture logs the navigation
        p.u.mem_write(0x20015000,struct.pack('<5I',0x1079,0,0,0,0));p.call(UU['fx_event'],v,0x20015000) # the Clipper footer toggle
        p.w(0x20016000,42);p.call(0x08145efc,v,0x20016000)
        self.assertEqual([struct.unpack('<H',p.u.mem_read(v+0x93c4+0x14+i*2,2))[0] for i in range(8)],[KEYS[16],KEYS[17],KEYS[18],0,0,0,0,0])
        self.assertEqual(p.text(p.r(v+0x93c8)),'Track 1 / Soft Clip');self.assertTrue(N.CHORD_EDITOR)
        r=0x20020000;self.assertNotIn(p.text(p.r(r+MODE*32+4)) if p.r(r+MODE*32+4) else '',('Mode','Level'))
if __name__=='__main__':gc.disable();unittest.main(verbosity=2)
