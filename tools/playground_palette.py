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
PLAYGROUND_TRACKS=[0xff81c5e8,0xffafb5f1,0xffd5a9db,0xffeca4ac,0xffe3ae83,0xffc9bc7b,0xff93ca9e,0xff75ccc8]
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
PAD_BRIGHT=[led(c) for c in PLAYGROUND_TRACKS]
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
