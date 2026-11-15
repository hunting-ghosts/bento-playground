"""Compile the MIT DaisySP engine and exact-version native adapters."""
from pathlib import Path
import subprocess,sys,struct,os
from keystone import Ks,KS_ARCH_ARM,KS_MODE_THUMB
ROOT=Path(__file__).resolve().parent
CODE=0x080d6000;WRAP=0x080d5800
ADAPTER_END=0x080d5950 # 16-byte guard before the bank-1 M4 cave at 080D5960
SYMS={}
EXTRA=[]
RT_VOICE=0 # R6.16: set by build_fx (ratchet player rt_voice) before writes_for
def compile_kick():
 v=ROOT/'vendor/daisysp/Source'
 extra=['-DBENTO_SYNCUSSION=1'] if os.environ.get('BENTO_SYNCUSSION')=='1' else []
 subprocess.run([sys.executable,'-m','ziglang','c++',*extra,'-target','thumb-freestanding-eabihf','-mcpu=cortex_m7+fp_armv8d16sp+fpregs+fpregs16+vfp4d16sp','-mfloat-abi=hard','-mfpu=fpv5-sp-d16','-Oz' if extra else '-Os','-flto','-g','-fno-exceptions','-fno-rtti','-ffreestanding','-fno-builtin','-fno-stack-protector','-ffunction-sections','-nostdlib','-nostdlib++','-I'+str(ROOT/'kick_support'),'-I'+str(v),'-I'+str(v/'Utility'),'-Wl,--entry=kick_render','-Wl,--script='+str(ROOT/'kick.ld'),str(ROOT/'kick.cpp'),str(v/'Drums/synthbassdrum.cpp'),str(v/'Drums/synthsnaredrum.cpp'),str(v/'Drums/hihat.cpp'),str(v/'Filters/svf.cpp'),'-o',str(ROOT/'kick.elf')],check=True)
 e=(ROOT/'kick.elf').read_bytes();o=struct.unpack_from('<I',e,32)[0];size,n=struct.unpack_from('<HH',e,46);ss=[struct.unpack_from('<10I',e,o+i*size) for i in range(n)]
 global EXTRA
 alloc=[s for s in ss if s[2]&2]
 EXTRA=[]
 bounds={0x080d1600:0x080d1f00,0x080d5100:0x080d5800}
 for s in alloc:
  if s[3]==CODE:continue
  if not extra or s[3] not in bounds or s[3]+s[5]>bounds[s[3]]:raise ValueError('Syncussion section outside declared application cave: '+hex(s[3])+' + '+hex(s[5]))
  EXTRA.append((s[3],e[s[4]:s[4]+s[5]]))
 alloc=[s for s in alloc if s[3]==CODE]
 if len(alloc)!=1 or alloc[0][3]!=CODE or CODE+alloc[0][5]+32>0x080da640:raise ValueError('Synth code must end before the R6.16 ratchet cave at 080DA640')
 global SYMS
 SYMS.clear()
 for s in ss:
  if s[1]!=2:continue
  tab=ss[s[6]];names=e[tab[4]:tab[4]+tab[5]]
  for i in range(0,s[5],s[9]):
   off,a,_,info,_,_=struct.unpack_from('<IIIBBH',e,s[4]+i)
   if info&15==2:SYMS[names[off:].split(b'\0')[0].decode()]=a&~1
 s=alloc[0];return e[s[4]:s[4]+s[5]]
def writes_for(stock,append):
 code=compile_kick();k=Ks(KS_ARCH_ARM,KS_MODE_THUMB)
 def asm(s,a):return bytes(k.asm(s,a)[0])
 # Fixed endpoint called from existing voice hook. Entry 9480 adapts native VFP pitch.
 # R6.16: every native sampler voice start first tells the ratchet player
 # (mono roll: release that note's previous hit), then the kick endpoint. The
 # adapters calling WRAP already saved r0-r12/lr and d0-d7.
 voice=asm(('push {r0,r1,r4,lr}; bl '+hex(RT_VOICE)+'; pop {r0,r1,r4,lr}; ' if RT_VOICE else '')+'b.w '+hex(SYMS['kick_voice']),WRAP)
 pitch=asm('push {r4,r5,r6,lr}; vpush {d8}; mov r4,r0; mov r5,r1; add.w r0,r5,#0x300; bl 0x0809fd80; vldr s16,[r4,#0x104]; vcvt.f32.s32 s16,s16; vldr s1,scale; vmul.f32 s16,s16,s1; vadd.f32 s0,s0,s16; bl 0x080518a0; vldr s1,[r5,#0x48]; vmul.f32 s0,s0,s1; vmov r0,s0; vpop {d8}; pop {r4,r5,r6,pc}; .align 2; scale: .word 0x38aec33e',0x080d5880)
 start=0x080d5900
 prefix='push.w {r0-r12,lr}; mrs r0,APSR; push {r0,r1}; vpush {d0-d7}; '
 restore='vpop {d0-d7}; pop {r0,r1}; msr APSR_nzcvq,r0; pop.w {r0-r12,lr}; '
 wrap=asm(prefix+'ldr r0,[sp,#72]; ldr r1,[sp,#76]; ldr r2,[sp,#128]; ldr r3,[sp,#132]; bl '+hex(SYMS['kick_render'])+'; cmp r0,#0; beq stock; '+restore+'movs r0,#1; bx lr; stock: '+restore+'push.w {r4-r11,lr}; b.w 0x08091824',start)
 payload=voice+bytes(0x80-len(voice))+pitch
 if len(payload)>0xf0:raise ValueError('Pitch adapter overlaps K7 assignment endpoint')
 payload+=bytes(0xf0-len(payload))+asm('b.w '+hex(SYMS['kick_enable']),WRAP+0xf0)
 payload+=asm('b.w '+hex(SYMS['kick_command_probe']),WRAP+0xf4)
 if os.environ.get('BENTO_SYNCUSSION')=='1':payload+=asm('b.w '+hex(SYMS['kick_sync_clock']),WRAP+0xf8)
 payload+=bytes(0x100-len(payload))+wrap
 # R6.11: the adapters end at ADAPTER_END; the zero gap up to CODE is no longer
 # part of this write (bank-1 M4 code may use it, see build_fx.UI_BANK1).
 # Image bytes are unchanged: the gap was written as zeros before.
 if WRAP+len(payload)>ADAPTER_END:raise ValueError('Kick adapters overlap the bank-1 M4 cave')
 payload+=bytes(-len(payload)%4)
 body=code+b"BENTO_MOD:daisy-kick:0.14.0:K7\0"
 body+=b"\xff"*(-len(body)%4)
 writes=[(WRAP,payload,bytes(len(payload)),'K7 live DaisySP kick adapters in verified-zero M7 application cave'),(CODE,body,bytes(len(body)),'K7 live DaisySP kick in verified-zero M7 application cave'),(0x08091820,asm('b.w '+hex(start),0x08091820),stock[0x08091820-0x08040000:0x08091824-0x08040000],'K7 native per-voice render entry; original path on ordinary samples')]
 for address,data in EXTRA:
  data+=bytes(-len(data)%4);before=stock[address-0x08040000:address-0x08040000+len(data)]
  if before!=bytes(len(data)):raise ValueError('Syncussion cave preimage is not exact zero')
  writes.append((address,data,before,'Syncussion in declared unused tail of existing application code reservation'))
 return writes
