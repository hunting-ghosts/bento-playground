"""Run 17 (owner, 13 Nov, saturator FINAL): the 1.6.8 Track FX saturator, measured through the C ABI of the
TF_SATURATOR build (libtrack_fx_sat.so) against the unchanged previous DSP (libtrack_fx.so).
clip_enabled packs On (bit 0), Mode (bit 1: 0 Soft, 1 Hard) and Level (bits 8-15, int8 dB); Drive d dB is
clip_ceiling_db = -d (track_fx.h). Host evidence only."""
import ctypes as C
import math,unittest
from pathlib import Path
import numpy as np
from test_track_fx import Settings,Meters,P,U,N,tone,rms
ROOT=Path(__file__).resolve().parents[1]
def load(name):
    lib=C.CDLL(str(ROOT/name))
    for f,a in {'tf_init':[P,C.c_float],'tf_configure':[P,U,C.POINTER(Settings)],'tf_get_settings':[P,U,C.POINTER(Settings)],'tf_process':[P,U,P,P,N],'tf_save':[P,P,N],'tf_load':[P,P,N],'tf_reset_track':[P,U]}.items():
        getattr(lib,f).argtypes=a;getattr(lib,f).restype=C.c_int
    for f in ['tf_bank_bytes','tf_record_bytes']:getattr(lib,f).restype=N
    lib.tf_defaults.argtypes=[C.POINTER(Settings)];return lib
OLD=load('libtrack_fx.so');SAT=load('libtrack_fx_sat.so')
def pack(on=1,hard=0,level=0):return (on&1)|(hard&1)<<1|(level&255)<<8
class Bank:
    def __init__(self,lib):
        self.lib=lib;self.raw=C.create_string_buffer(lib.tf_bank_bytes()+64);self.p=(C.addressof(self.raw)+31)&~31;assert lib.tf_init(self.p,48000)
    def config(self,track=0,**kw):
        s=Settings();self.lib.tf_defaults(C.byref(s));s.auto_makeup=0
        for k,v in kw.items():setattr(s,k,v)
        return self.lib.tf_configure(self.p,track,C.byref(s))
    def process(self,x,track=0,block=64,right=True):
        l=np.array(x,dtype='float32',copy=True);r=(-l).copy() if right else None
        for i in range(0,len(l),block):assert self.lib.tf_process(self.p,track,l.ctypes.data+i*4,None if r is None else r.ctypes.data+i*4,min(block,len(l)-i))
        return (l,r) if right else l
def sat(x,drive,hard=0,level=0,settle=True):
    """Settled saturator output for x: the parameter smoothing (20 ms) has finished before x is measured."""
    b=Bank(SAT);assert b.config(clip_enabled=pack(1,hard,level),clip_ceiling_db=-drive)
    if settle:b.process(np.zeros(9600,'float32'),right=False)
    return b.process(x,right=False)
def harmonics(y,f0=1000,rate=48000,n=12):
    w=np.hanning(len(y));sp=np.abs(np.fft.rfft(y*w));k=len(y)*f0/rate
    return [float(sp[int(round(k*h))-2:int(round(k*h))+3].max()) for h in range(1,n+1)]
class Tests(unittest.TestCase):
    def test_bank_size_and_record_are_unchanged(self):
        self.assertEqual(SAT.tf_bank_bytes(),OLD.tf_bank_bytes());self.assertLessEqual(SAT.tf_bank_bytes(),0x1440) # no Track FX RAM growth
        self.assertEqual(SAT.tf_record_bytes(),OLD.tf_record_bytes())
    def test_old_ceiling_settings_are_bit_exact_soft_level_0(self):
        """An old project's ceiling c dB is Drive -c dB (Soft, Level 0 dB): identical bytes to the previous clipper,
        incl. enabling/disabling fades, ceiling changes while playing, EQ and compressor in front, stereo."""
        rng=np.random.default_rng(17);x=(rng.standard_normal(48000)*.7).astype('float32')
        for c in range(-12,1):
            for extra in ({},{'eq_enabled':1,'low_db':6,'mid_db':-4,'high_db':3},{'comp_enabled':1,'threshold_db':-20,'ratio':4}):
                a=Bank(OLD);b=Bank(SAT)
                for bank in (a,b):assert bank.config(clip_enabled=1,clip_ceiling_db=c,**extra)
                ya=a.process(x);yb=b.process(x)
                for bank in (a,b):assert bank.config(clip_enabled=0,clip_ceiling_db=max(c-3,-12),**extra) # fade out while moving
                za=a.process(x[:12000]);zb=b.process(x[:12000])
                for p,q in ((ya,yb),(za,zb)):self.assertEqual(p[0].tobytes(),q[0].tobytes(),(c,extra));self.assertEqual(p[1].tobytes(),q[1].tobytes(),(c,extra))
    def test_soft_and_hard_transfer_curves_differ(self):
        """Static curve with a slow ramp: Hard = identity up to the clip level then a sharp corner (flat),
        Soft = rounded knee (SoftClip: below the clip level at the corner, flat only beyond 3x)."""
        for drive in (0,6,12,24):
            k=10**(-drive/20);x=np.linspace(-4*k,4*k,20001).astype('float32')
            hard=sat(x,drive,1);soft=sat(x,drive,0)
            inside=np.abs(x)<=k*.999
            np.testing.assert_allclose(hard[inside],x[inside],rtol=2e-6,atol=1e-9)        # identity below the corner
            self.assertAlmostEqual(float(hard.max()),k,places=6);self.assertAlmostEqual(float(hard.min()),-k,places=6)
            at=np.argmin(np.abs(x-k));self.assertLess(soft[at],.8*k);self.assertAlmostEqual(float(hard[at]),k,delta=k*1e-3) # knee
            self.assertTrue(np.all(np.abs(soft)<=k*(1+1e-6)))
            beyond=np.abs(x)>=3*k*1.001;np.testing.assert_allclose(np.abs(soft[beyond]),k,rtol=1e-6)
            d=np.diff(soft)/np.diff(x);self.assertLess(float(np.abs(np.diff(d)).max()),.05) # no corner in Soft
            dh=np.diff(hard)/np.diff(x);self.assertGreater(float(np.abs(np.diff(dh)).max()),.9) # Hard corner: slope 1 -> 0
    def test_sine_spectra_are_odd_and_hard_is_brighter(self):
        """0 dBFS 1 kHz sine. Drive 0: the clip level equals the peak, so Hard leaves it clean while Soft's rounded
        knee already adds a third harmonic. Drive 3..12 dB: both add odd harmonics only, Hard clearly more of the high
        ones (7th and up); towards 24 dB both approach a square wave (measured: +22.6/+12.7/+4.3/+2.2/+0.1 dB)."""
        x=tone(1000,1,amp=1.0);high=lambda h:math.sqrt(sum(v*v for v in h[6:]))/h[0]
        hs=harmonics(sat(x,0,0));hh=harmonics(sat(x,0,1))
        self.assertGreater(hs[2]/hs[0],.05);self.assertLess(hh[2]/hh[0],1e-5)
        for drive,margin in ((3,15),(6,10),(12,4),(18,1)):
            hs=harmonics(sat(x,drive,0));hh=harmonics(sat(x,drive,1))
            for h in (hs,hh):
                self.assertLess(max(h[1::2])/h[0],1e-3)        # even harmonics absent (odd-symmetric curves)
                self.assertGreater(h[2]/h[0],.05)              # a real third harmonic
            self.assertGreater(20*math.log10(high(hh)/high(hs)),margin,drive) # Hard is brighter than Soft
    def test_automatic_compensation_keeps_small_signals_and_more_drive_is_not_louder(self):
        quiet=tone(500,.5,amp=.01);loud=tone(500,.5,amp=1.0);last=None
        for drive in range(0,25,3):
            for hard in (0,1):
                y=sat(quiet,drive,hard);self.assertAlmostEqual(20*math.log10(rms(y)/rms(quiet)),0,delta=.05 if hard else .2,msg=drive)
            r=rms(sat(loud,drive,0))
            if last is not None:self.assertLessEqual(r,last*1.0001,drive)
            last=r
    def test_level_scales_the_output_after_the_curve(self):
        x=tone(500,.5,amp=.5)
        for level in (-12,-6,3,12):
            ref=sat(x,6,1,0);y=sat(x,6,1,level)
            np.testing.assert_allclose(y,ref*np.float32(10**(level/20)),rtol=1e-5,atol=1e-7)
    def test_level_change_is_smoothed(self):
        b=Bank(SAT);assert b.config(clip_enabled=pack(1,1,0),clip_ceiling_db=0);b.process(np.zeros(4800,'float32'),right=False)
        assert b.config(clip_enabled=pack(1,1,-12),clip_ceiling_db=0);y=b.process(np.full(19200,.5,'float32'),right=False) # 20 ms smoothing
        self.assertGreater(float(y[0]),.49);self.assertLess(float(np.abs(np.diff(y)).max()),.01);self.assertAlmostEqual(float(y[-1]),.5*10**(-12/20),places=3)
    def test_invalid_packed_values_and_ranges_fail_atomically(self):
        b=Bank(SAT)
        for word,c in ((pack(1,0,13),-1),(pack(1,0,-13),-1),(pack(1)|4,-1),(pack(1)|1<<16,-1),(pack(1),-24.5),(pack(1),.5)):
            self.assertEqual(b.config(clip_enabled=word,clip_ceiling_db=c),0,(hex(word),c))
        self.assertEqual(b.config(clip_enabled=pack(1,1,-12),clip_ceiling_db=-24),1)
    def test_record_keeps_mode_level_and_drive(self):
        b=Bank(SAT);assert b.config(track=3,clip_enabled=pack(1,1,-7),clip_ceiling_db=-20)
        r=C.create_string_buffer(SAT.tf_record_bytes());assert SAT.tf_save(b.p,r,len(r))
        c=Bank(SAT);self.assertEqual(SAT.tf_load(c.p,r,len(r)),1);s=Settings();assert SAT.tf_get_settings(c.p,3,C.byref(s))
        self.assertEqual((s.clip_enabled,s.clip_ceiling_db),(pack(1,1,-7),-20.0))
    def test_disabled_saturator_ignores_mode_and_level(self):
        x=tone(700,.2,amp=.9);b=Bank(SAT);assert b.config(clip_enabled=pack(0,1,-12),clip_ceiling_db=-24)
        y=b.process(x,right=False);self.assertEqual(y.tobytes(),x.tobytes()) # bypass, track asleep
if __name__=='__main__':unittest.main()
