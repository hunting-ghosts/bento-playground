"""Playground palette for a built bento1.bin (screen colours only, no code).

Changes, all reversible with --revert:
- five CLUT words in the UI core's initialised data (flash source of RAM 30000000,
  stock at 081B3E38; found by its exact stock contents):
  [0]+[1] background (index 0: unset icon pixels), [2] white/text, [3] lines, [4] record red, [6] dim text.
  Index 5 stays unchanged. The eight track colours (7..14) become the Playground
  track colours (owner's design), mapped by track number; --native-tracks keeps them.
- the LTDC background colour (BCCR), written once by HAL_LTDC_Init on the M7 core
  (080446BA/C2/CC load Backcolor Green/Red/Blue from the zeroed handle). The three
  loads become immediates. CLUT[1] and BCCR must match, otherwise glyph edges
  and every alpha level blend towards black.

- the pad LED colour per track (bright 08140EF0, dim 08140F50, used for track
  colours on the pads): both functions become an 8-entry table lookup with the
  Playground track hues made LED-friendly (same hue, saturation x2.2, full value;
  dim = 100/255 of bright). Other indices keep the stock default. Tune after a
  hardware photo.

usage: python playground_palette.py IN.bin OUT.bin [--native-tracks] [--revert]
"""
import struct,sys,hashlib

BASE=0x08040000
STOCK_CLUT=[0xff000000,0xff000000,0xffffffff,0xff333333,0xffbb2222,0xff22bb22,0xff7f7f7f,
            0xff00ccff,0xff0fff00,0xfff00000,0xfffff800,0xffff6600,0xffcc00ff,0xffff00ff,0xff00ffcc]
# [0] = background too: native icons paint their unset pixels with index 0 (0xF0).
# Owner (27 Oct): background stays stock black, not the G1-G3 charcoal.
PLAYGROUND={0:0xff000000,1:0xff000000,2:0xffe9eeea,3:0xff3b4142,4:0xfff27979,6:0xffa0aaa9}
# Playground track colours by track number. CLUT index per track (from native renders):
# track 1..8 -> 7, 8, 9, 10, 11, 14, 13, 12.
TRACK_INDEX=[7,8,9,10,11,14,13,12]
# Owner choice C (26 Oct): hue wheel with even brightness, opal-inspired hues, starting with blue:
# sky, perano, lovecloud, rose, amber, sun beam, mint, teal.
# R6.9 tried the list rotated one track left; owner reverted it (8 Nov).
# R6.15 (owner, 9 Nov): palette 3C "Electric pastel" - tracks 1-3 new, 4-8 unchanged.
PLAYGROUND_TRACKS=[0xff699fd8,0xffab9bf0,0xffd49ee0,0xffeca4ac,0xffe3ae83,0xffc9bc7b,0xff93ca9e,0xff75ccc8]
TRACKS=dict(zip(TRACK_INDEX,PLAYGROUND_TRACKS))
import colorsys
def led(argb):
    r,g,b=((argb>>k)&255 for k in (16,8,0));h,s_,v=colorsys.rgb_to_hsv(r/255,g/255,b/255)
    return tuple(round(x*255) for x in colorsys.hsv_to_rgb(h,min(1,s_*2.2),1))
def pad_fn(addr,table,default):
    from keystone import Ks,KS_ARCH_ARM,KS_MODE_THUMB
    src=("cmp r0,#7\nbhi d\nadr r1,t\nldr.w r0,[r1,r0,lsl #2]\nbx lr\nd: ldr r0,v\nbx lr\n.align 2\n"
         "t: .word "+",".join(hex(x) for x in table)+"\nv: .word "+hex(default))
    enc,_=Ks(KS_ARCH_ARM,KS_MODE_THUMB).asm(src,addr);return bytes(enc)
_rgb=lambda c:(c[0]<<16)|(c[1]<<8)|c[2]
# R6.16 (owner, 9 Nov, hardware): LEDs do not match the screen - green and red
# LEDs look much stronger than blue. Track 1 looked too cyan and glaring, track 2's
# violet looked like track 3's pink. Hand-set pad values for those tracks (index
# = track-1); the others keep the automatic mapping. Tune further by eye.
# P168 exp3 (owner, 11 Nov, hardware, on (00,38,E0)/(2A,18,F0)): track 1 still too cyan,
# track 2 not violet enough; pure blue may be too bright. The green LED is the strong one,
# so track 1 loses most of its green (38 -> 14: blue with a trace of azure, still apart
# from track 2) and a little blue (E0 -> D8) against glare. Track 2 gets more red and no
# green (violet = blue + red; the automatic value (5C,38,FF) had looked pink because of its
# green, (2A,18,F0) too blue): (48,00,E8). Pad LED values only; the screen colours stay.
# Owner-judged on hardware; tracks 3-8 unchanged.
# P168 exp4 (owner, 11 Nov, hardware, on (00,14,D8)/(48,00,E8)): track 1 "a bit too much into the dark
# blue, needs a tiny bit more cyan"; track 2 "off: needs to be darker and bluer, closer to what the first
# Playground had" (first Playground LED 65,73,FF from screen 0xAFB5F1). Owner via coordinator: track 2 must
# stay clearly violet against track 1's blue, and both need the PASTEL feel of tracks 3-8 (which contain some
# of every LED channel because they come from the screen colour by led()). So tracks 1-2 are no longer
# hand-picked saturated values: start from led() of their screen colours (0x699FD8 -> 00,7C,FF;
# 0xAB9BF0 -> 5E,38,FF) and pull toward the owner's direction:
#   track 1 (12,34,D0): less cyan than 00,7C,FF, a little more than 00,14,D8 (hue 229 deg instead of 234),
#     a trace of red for the pastel feel, a little less blue against glare;
#   track 2 (44,18,D0): bluer (hue 254 instead of 259) and darker than 48,00,E8, a trace of green for the
#     pastel feel, still clearly violet: about 25 deg of hue from track 1, as before.
# The brightness balance below leaves both as they are (drive 294 and 307, under 450 * 1.07; it never
# brightens). Owner-judged on hardware; tracks 3-8 unchanged.
PAD_OVERRIDE={0:(0x12,0x34,0xD0),1:(0x44,0x18,0xD0)}
# P168 exp3, run 5 (owner, 11 Nov: all tracks should feel evenly bright, pure blue must not stick out).
# No measurement exists, so this is a rule, not a calibration: drive = R + 1.3 G + B (the green LED is
# the strong one, owner R6.16); a track whose drive is more than 7 % above 450 (the level of tracks 4
# and 5) is scaled down to it, same hue; nothing is made brighter, so tracks 1 and 2 (242 and 304: one
# or two LEDs only) stay as the owner last judged them and the blue is not pushed.
# Result (bright): 3 E1 5A FF -> AA 44 C0, 6 FF DB 25 -> C7 AB 1D, 7 66 FF 85 -> 51 CB 6A,
# 8 10 FF F4 -> 0C C2 BA; tracks 4 (FF 54 67) and 5 (FF 7C 12) unchanged. Owner-judged on hardware.
PAD_LEVEL=450
def balanced(c):
    drive=c[0]+1.3*c[1]+c[2]
    return c if drive<=PAD_LEVEL*1.07 else tuple(round(x*PAD_LEVEL/drive) for x in c)
PAD_BRIGHT=[PAD_OVERRIDE.get(i) or balanced(led(c)) for i,c in enumerate(PLAYGROUND_TRACKS)]
PAD_DIM=[tuple(round(x*100/255) for x in c) for c in PAD_BRIGHT]
PADS=[  # (address, stock bytes (prefix of the function), Playground bytes)
    (0x08140EF0,bytes.fromhex('08b507281cd8dfe800f0041e070a0c0e111442f6ff5008bd4ff47f00fbe70c48f9e70c48f7e74ff6cc70f4e74ff0ff10f1e70948e4f716fd40b14ff0ff10eae7'),None),
    (0x08140F50,bytes.fromhex('08b507281cd8dfe800f0041d070a0c0e111441f27d4008bd4ff44810fbe70c48f9e70c48f7e746f24640f4e74ff06410f1e70948e4f7e6fc38b14ff06410eae7'),None)]
def pads():
    out=[]
    # defaults for indices > 7 as in stock: bright 0xFFFFFF, dim 0x64FFFF (literal 08140FAC)
    for (a,stock,_),tab,dflt in zip(PADS,(PAD_BRIGHT,PAD_DIM),(0xffffff,0x64ffff)):
        new=pad_fn(a,[_rgb(c) for c in tab],dflt)
        assert len(new)<=len(stock);out.append((a,stock[:len(new)],new))
    return out
BG=PLAYGROUND[1]
def mov_w(rd,imm8):  # T2 MOV.W rd,#imm8
    return struct.pack('<HH',0xF04F,(rd<<8)|imm8)
BCCR=[  # (address, stock bytes, Playground bytes)
    (0x080446BA,bytes.fromhex('92f83500'),mov_w(0,(BG>>8)&255)),   # Green
    (0x080446C2,bytes.fromhex('92f836c0'),mov_w(12,(BG>>16)&255)), # Red
    (0x080446CC,bytes.fromhex('92f83410'),mov_w(1,BG&255)),        # Blue
]

def find_clut(img,words):
    pat=struct.pack('<15I',*words)
    i=img.find(pat)
    if i<0 or img.find(pat,i+1)>=0: return None
    return i

def apply(img,revert=False,tracks=True):
    img=bytearray(img)
    table={**PLAYGROUND,**(TRACKS if tracks else {})}
    measure=[table.get(k,w) for k,w in enumerate(STOCK_CLUT)]
    src,dst=(measure,STOCK_CLUT) if revert else (STOCK_CLUT,measure)
    off=find_clut(img,src)
    if off is None: raise SystemExit('CLUT not found exactly once (already patched, or a different image)')
    img[off:off+60]=struct.pack('<15I',*dst)
    for a,stock,new in BCCR+(pads() if tracks else []):
        o=a-BASE; want,put=(new,stock) if revert else (stock,new)
        n=len(want)
        if bytes(img[o:o+n])!=want: raise SystemExit(f'guard failed at {a:08X}: {bytes(img[o:o+n]).hex()}')
        img[o:o+n]=put
    return bytes(img),BASE+off

if __name__=='__main__':
    inp,out=sys.argv[1],sys.argv[2]; rev='--revert' in sys.argv
    data=open(inp,'rb').read()
    res,at=apply(data,rev,'--native-tracks' not in sys.argv)
    assert len(res)==len(data) and len(res)%4==0
    open(out,'wb').write(res)
    print(('reverted' if rev else 'Playground palette'),'CLUT at',hex(at),'sha256',hashlib.sha256(res).hexdigest())
