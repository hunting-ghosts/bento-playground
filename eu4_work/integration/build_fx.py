"""Hash-guarded EU10 Euclidean + TF2 extension on the exact K16 build. No bootloader."""
from pathlib import Path
import struct,sys,subprocess,hashlib,json,os
from keystone import Ks,KS_ARCH_ARM,KS_MODE_THUMB
R=Path(__file__).resolve().parent
BASE=0x08040000;AUDIO=0x080dc400;UI_STUB=0x081bd8c0;UI=UI_STUB+0x660 # space (1.6.8 port): was +0x800; stub adapters use 1,602 B (R6.18 black box +52)
UI_PADS=[(0x081b4c00,0x081b5000),(0x081b5400,0x081b5800),(0x081b5900,0x081b6000),
         (0x081b6300,0x081b6600),(0x081b6a00,0x081b7000),
         (0x081b9420,0x081ba000),(0x081bc6a0,0x081bd000),(0x081bd180,0x081bd800),
         (0x081b70d0,0x081b7400),(0x081bac80,0x081bb000),
         (0x081b3fc0,0x081b40f0),(0x081b66d0,0x081b67f0)];UI_PAD=[]
# Space (1.6.8 port): .pad6/.pad7 are zero runs 081B3FAB..081B4100 and
# 081B66B6..081B6800 of the K16 image, zero in stock 1.6.1, K16, R6.15 and
# the shrunk builds, no word or branch in those images points into them; each
# keeps a 16-byte guard at both ends. Filled only by the build-time pad filler.
# R6.6: two more zero runs in the K16 append (081B70BC..081B7400 and
# 081BAC64..081BB000): zero in K16, zero in the R6.5 image, no absolute word
# in the image points into them; each starts 16 bytes into its run (guard).
# New ranges are zero-filled K16 append padding after controls, mixer helpers,
# condition adapters/labels and hold-step code; none is a native asset.
# Retired K16 C bodies only; all original four-byte forwarding entries remain.
# The live native encoder wrapper owns 081BC660..081BC6A0.
# No native resources or bitmap pixels are part of these regions.
UI_RETIRED=[(0x081b4a00,0x081b4c00),(0x081b5070,0x081b5200),
            (0x081b7404,0x081b76ac),(0x081b76b0,0x081b78b8),(0x081b78bc,0x081b7c5c),
            (0x081b7c60,0x081b7fb4),(0x081b80c8,0x081b8c00),
            (0x081b8c04,0x081b8d00),(0x081b8d04,0x081b8e00),
            (0x081b8e04,0x081b9000),(0x081b9004,0x081b9410),
            (0x081bbd08,0x081bc660)]
# R6.11 bank-1 M4 code: verified stock-zero runs in the M7 flash bank
# (080D5946..080D6000 between the kick adapters and the kick code;
# 080DBCBA..080DC000 after the P14 adapters). Each starts 16+ bytes into its run
# (guard). Usable by the M4 only with the widened MPU (BENTO_M4_MPU_WIDE=1,
# region 1 = 08000000/2 MB); the build refuses bank-1 M4 code otherwise.
# 080D08AE..080D1000 stays with seqfx (M7).
UI_BANK1=[(0x080d5960,0x080d6000),(0x080dbcd0,0x080dc000),
          (0x080d0510,0x080d0800),(0x080d1180,0x080d1400),(0x080d1f20,0x080d2000),(0x080d2140,0x080d2400),(0x080d3190,0x080d33c0)]
# zero in stock, K16, R6.10 and R6.14 (R6.14 caves: no pointers into them; the
# PLAY code at 080D0200/080D0300 is bounded below 080D0500, see play_input/play_bank)
BANK1_RUNS=[(0x080d5946,0x080d6000),(0x080dbcba,0x080dc000),(0x080d0500,0x080d0800),(0x080d1170,0x080d1400),(0x080d1f10,0x080d2000),(0x080d2130,0x080d2400),(0x080d3180,0x080d33c0)]
UI_ADAPTER_TAIL=None
PAD_RESERVE=8 # bytes kept free per pad by the pad filler (layout parameter)
BANK1B=0x080dbcd0 # .bank1b start; the P14 adapters must end 16 bytes below it
RT_CAVE=(0x080cf4c0,0x080cfff0);RT_RUN=0x080cf4a0 # R6.13: stock zero 080CF499..080D0000
# Ratchet player slots (version layout; 1.6.1: one slot = RT_CAVE, checked from RT_RUN).
RT_SLOTS=[RT_CAVE];RT_FUNCTION_SECTIONS=False
RT2_CAVE=(0x080da640,0x080dabf0) # R6.16c: stock-zero tail of the Kick code reservation (Kick code now ends <= 080DA620), no pointers into it
K16_SHA='5e72971b31388201454a71b0be7cc61ad40915bda3a75e635d104dd89346a03d'
# Native adapters and compiled-code fixtures call these across ELF boundaries.
# LTO must retain their external identity, even when all C callers are inlined.
UI_EXPORTS="""fx_value_text fx_value_fmt bb_boot bb_card tr_tick tr_block tr_get tr_set tr_lights chord_pad_pitch chord_project_scale arp_diag arp_publish bars_bind bars_count bars_event bars_header bars_index bars_names bars_registry bars_set bars_text bars_title browser_list_hook browser_list_add browser_request
chord_bank chord_capture chord_clear_current chord_diatonic chord_event chord_get chord_header chord_keys_snapshot chord_live_active chord_live_event chord_live_header chord_live_hw chord_live_owner chord_live_tap  chord_mail_serial chord_nav chord_open_from_seq chord_piano_event chord_pub_serial chord_state_slot chord_toolbar chord_track_tick chord_view_set chord_view_visible
drum_cache_slot bb_watchdog card_poll card_idle_wait drum_copy_capture drum_copy_forget drum_eu_view drum_tab_mismatch  eu_drum_title eu_gate_notes eu_note_name eu_repitch  eu_shared_scratch eu_vel_names eu_velocity eu_view_capture
fx_event fx_finish fx_get fx_header fx_load fx_nav fx_save fx_screen_active fx_screen_bar fx_screen_hit fx_screen_select fx_screen_snapshot fx_screen_meter_snapshot fx_toolbar
header_action header_action_lit header_fixed_action header_fixed_tab header_remove_undo header_sync  inst_bank_state_slot lane_state_slot
kit_seq_after kit_seq_bind kit_seq_dispatch kit_seq_event kit_seq_header_reset kit_seq_holding kit_seq_increment kit_seq_lights kit_seq_nav kit_seq_periodic kit_seq_point kit_seq_signature kit_seq_state_slot kit_seq_toolbar kit_seq_touch kit_seq_touch_context kit_seq_value kit_seq_value_hit kick_base_value locks_direct_edit locks_direct_kind locks_direct_scratch locks_direct_value
kit_seq_strip_snapshot kit_seq_strip_touch kit_seq_step_focus kit_seq_strip_bind kit_seq_step_event kit_seq_step_touch locks_step_snapshot locks_step_edit locks_step_registry locks_step_choice
live_assign_pitch live_begin live_cycle live_cycle_restore live_cycle_snapshot live_cycle_steps live_dynamic live_edit live_finish live_generate live_lanes live_load live_mel_unit live_pitch_owner live_position live_row_pitch live_save live_set_gate live_value
macro_armed macro_binding_tap macro_disarm macro_existing_slot macro_increment macro_load macro_model_event macro_overlay macro_periodic macro_preservation_fault macro_project_reset macro_readout macro_save macro_save_blocked macro_save_request macro_select macro_snapshot macro_state_slot macro_title macro_touch macro_view_set
mel_audio_prepare melodic_lock_pack melodic_lock_registry melodic_lock_state_slot melodic_locks_choose melodic_locks_event melodic_locks_header melodic_locks_menu melodic_locks_proj melodic_locks_touch melodic_locks_touch_context melodic_register_tracks mod_state_slot native_fx_event native_fx_page native_fx_view_slot
perf_bar_down perf_bar_kind perf_bar_up perf_chord_share perf_chord_shared perf_dispatch perf_display_state perf_event perf_get perf_header perf_load perf_macro_focus perf_macro_targets perf_macro_view perf_nav perf_navigation perf_notes_name perf_pad perf_page_active perf_point_hit perf_readout perf_save perf_state_slot perf_tick
pg_fx_touch_down pg_fx_touch_up pg_grid_prepare pg_launch_toolbar pg_mixer_bar_drag pg_mixer_compressor pg_mixer_toolbar pg_perform_tick pg_tracks_nav
piano_after_header piano_current_view piano_custom_view piano_eu_event piano_eu_header piano_eu_nav piano_eu_slot piano_eu_toolbar piano_event piano_mode_set piano_one_shot piano_select_all piano_select_toggle piano_selecting
play_mute_bank play_mute_dispatch playground_existing_slot playground_state_slot seq_auto_arm seq_auto_take seq_eu_active seq_eu_encoder seq_eu_grid seq_eu_header seq_eu_leave seq_eu_mode seq_eu_tab seq_eu_tick seq_follow seq_location seq_nav_event seq_nav_global seq_nav_menus  step_current_view step_unit
workflow_lock_tap workflow_nav workflow_periodic workflow_state_slot""".split()
# Run 13 (space, P168 exp8): more K16 append padding for the pad filler, location only (no code change).
# Zero runs between the K16 wrapper stubs (UI startup/selection 081B5200..081B5400, kick_install wrappers
# 081BA000..081BA200, kick_ui wrappers 081BB000..081BB400): zero in stock and K16, a 16-byte zero guard at
# both ends, and no branch, word or MOVW/MOVT pair of the K16 image points into them (_k16_unreferenced).
# Not used: the explicit entry 081BA1C0 (kick_ui.c calls it through a computed address) keeps its guard.
RUN13_PADS=[(0x081b5284,0x081b52f0),(0x081b5378,0x081b53f0),(0x081ba03c,0x081ba070),(0x081ba0c0,0x081ba0f0),
            (0x081ba140,0x081ba1b0),(0x081bb094,0x081bb0f0),(0x081bb154,0x081bb1f0),(0x081bb23c,0x081bb2f0),(0x081bb33c,0x081bb3f0)]
UI_PADS+=RUN13_PADS
# The K16 condition display stubs 081B5800..081B5894 (five entries, conditions.py of K16) are dead in this
# build: their five native sites now branch to the bank-1 note helpers (note_helper below). The stubs and the
# zero tail up to a 16-byte guard before 081B5900 become one more retired body; the build checks the five sites.
RUN13_RETIRED_STUBS=(0x081b5800,0x081b58f0);RUN13_STUB_SITES=[0x08159b80,0x0815c3d2,0x0815c8b4,0x08158f1c,0x08158a7c]
UI_RETIRED+=[RUN13_RETIRED_STUBS]
def _branch_targets(img):
 """Every Thumb-2 BL/B.W/B<cond>.W target, aligned word and MOVW/MOVT pair value of an image (BASE-based)."""
 h=struct.unpack('<%dH'%(len(img)//2),img[:len(img)//2*2]);out=set();movw={}
 for i in range(len(h)-1):
  h1,h2=h[i],h[i+1];a=BASE+2*i
  if i%2==0:out.add(h1|h2<<16)
  if (h1>>11)==0x1e:
   S=(h1>>10)&1;J1=(h2>>13)&1;J2=(h2>>11)&1
   if (h2&0xd000) in (0xd000,0x9000):
    o=(S<<24)|((1-(J1^S))<<23)|((1-(J2^S))<<22)|((h1&0x3ff)<<12)|((h2&0x7ff)<<1);out.add(a+4+o-(S<<25))
   elif (h2&0xd000)==0x8000:
    o=(S<<20)|(J2<<19)|(J1<<18)|((h1&0x3f)<<12)|((h2&0x7ff)<<1);out.add(a+4+o-(S<<21))
  if (h1&0xfbf0) in (0xf240,0xf2c0) and not h2&0x8000:
   imm=((h1&0xf)<<12)|((h1>>10&1)<<11)|((h2>>12&7)<<8)|(h2&0xff);rd=(h2>>8)&0xf
   if h1&0x80:
    if rd in movw and a-movw[rd][0]<64:out.add(imm<<16|movw[rd][1])
   else:movw[rd]=(a,imm)
 return out
def _k16_unreferenced(base,ranges):
 t=_branch_targets(base)
 for lo,hi in ranges:
  hit=sorted(x for x in t if lo<=(x&~1)<hi)
  assert not hit,('K16 image points into run-13 pad %08X..%08X'%(lo,hi),[hex(x) for x in hit[:4]])
def elf(path):
 b=path.read_bytes();off=struct.unpack_from('<I',b,32)[0];step,n=struct.unpack_from('<HH',b,46);ss=[struct.unpack_from('<10I',b,off+i*step) for i in range(n)];chunks=[];syms={}
 for s in ss:
  if s[2]&2:chunks.append((s[3],b[s[4]:s[4]+s[5]]))
  if s[1]!=2:continue
  st=ss[s[6]];tab=b[st[4]:st[4]+st[5]]
  for i in range(0,s[5],s[9]):
   name,value,size,info,_,idx=struct.unpack_from('<IIIBBH',b,s[4]+i)
   if info&15 in (1,2):syms[tab[name:].split(b'\0')[0].decode()]=value&~1 if info&15==2 else value
 return chunks,syms
if os.environ.get('BENTO_NATIVE_MOTION')=='1':
 raise SystemExit('W2 is workflow-only; recorder builds remain preserved at release/w1')
RT_CODE=None;RT2_CODE=None;RT_SYMS=None;MEL_CODE=None;MEL_SYMS=None;SEND_CODE=None;SEND_SYMS=None;NATIVE_LOCK=None;ARP_CODE=None;ARP_SYMS=None;CONTROLS_CODE=None;SEQFX_CODE=None;SEQFX_SYMS=None
import native_ids as _ids
# P168 exp8 (run 13): XY per-track send, 1.6.8 only. Its native addresses live in port/xy_168.py and port/xy_ui.c,
# which the port translation leaves alone (files in a directory named "port"); 1.6.1 compiles an empty unit.
XY=None
if _ids.BENTO_FW==168:
 sys.path.insert(0,str(R/'port'));import xy_168 as XY;import fxv_168 as FXV;sys.path.pop(0) # FXV: FX button views (port/fxv_168.py)
 UI_EXPORTS+=['xy_bar','xy_receive','xy_state','xy_tick','xy_toggle_track']+FXV.EXPORTS
JUMP_TABLES=['-mllvm','-min-jump-table-entries=3'] if _ids.BENTO_FW==168 else []
def _relink_with_outliner(result,out):
 """Space (1.6.8 port): with -flto the code is generated inside the linker, where
 zig cc does not forward -mllvm, so the machine outliner never ran (1 outlined
 function). Re-run zig's own ld.lld command, captured via ZIG_VERBOSE_LINK, with
 the outliner enabled. Fails closed unless exactly one link command targets out.
 -align-loops=1: the LTO code generator padded loop heads to 4 bytes (about 430
 two-byte NOPs, 0.9 KB of the UI text); padding only, no instruction changes.
 JUMP_TABLES (1.6.8 only, P168 exp6: room for the owner's PROJ footer fixes): -min-jump-table-entries=3 lets
 a switch with three cases use a table branch instead of a compare chain (LLVM default 4); same results,
 about 40 B smaller. Not on 1.6.1: there it grows code in the fixed .kitcontext cave past its bound.
 --icf=safe (P168 exp7 shrink): lld folds functions/read-only sections with identical bytes and relocations
 whose address is not significant (the compiler's address-significance table; functions whose address is taken
 or compared are never folded). Same instructions run, about 430 B smaller."""
 sys.stderr.write('\n'.join(l for l in result.stderr.splitlines() if not l.startswith('ld.lld '))+'\n')
 cmds=[l.split() for l in result.stderr.splitlines() if l.startswith('ld.lld ')]
 assert len(cmds)==1,'expected exactly one captured UI link command'
 cmd=cmds[0];assert cmd[cmd.index('-o')+1]==str(out),'captured link writes another file'
 r=subprocess.run([sys.executable,'-m','ziglang','ld.lld','-mllvm','-enable-machine-outliner=always','-mllvm','-align-loops=1',*JUMP_TABLES,'--icf=safe',*cmd[1:]],stderr=subprocess.PIPE,text=True)
 if r.returncode:sys.stderr.write(r.stderr);raise subprocess.CalledProcessError(r.returncode,r.args,stderr=r.stderr)
def _native_symbol_script(script):
 """Space (1.6.8 port): NFN(0x...) calls become direct BL to NAT_<token>.
 The symbol values are generated from the sources (Thumb bit set) into a
 temporary linker script that then includes the real one."""
 import re,tempfile
 toks=set()
 for d in (R,R.parents[1]/'chord_work',R.parent/'drums',R/'port'):
  for f in list(d.glob('*.c'))+list(d.glob('*.h')):toks|=set(re.findall(r'(?<![A-Za-z0-9_])NFN\((0x[0-9a-fA-F]{8}u?),',f.read_text(errors='replace')))
 fd,path=tempfile.mkstemp(suffix='.ld',prefix='ui_natives_')
 with os.fdopen(fd,'w') as f:
  for t in sorted(toks):f.write('NAT_%s = 0x%08x;\n'%(t,int(t.rstrip('uU'),16)|1))
  f.write('INCLUDE "%s"\n'%Path(script))
 return path
def _elf_layout(path):
 b=path.read_bytes();off=struct.unpack_from('<I',b,32)[0];step,n=struct.unpack_from('<HH',b,46)
 ss=[struct.unpack_from('<10I',b,off+i*step) for i in range(n)];st=ss[struct.unpack_from('<H',b,50)[0]];nm=b[st[4]:st[4]+st[5]]
 secs={nm[x[0]:].split(b'\0')[0].decode():(x[3],x[5]) for x in ss if x[2]&2}
 fns=[]
 for x in ss:
  if x[1]!=2:continue
  t=ss[x[6]];tab=b[t[4]:t[4]+t[5]]
  for i in range(0,x[5],x[9]):
   a,v,z,info,_,idx=struct.unpack_from('<IIIBBH',b,x[4]+i)
   if info&15==2 and z:fns.append((tab[a:].split(b'\0')[0].decode(),v&~1,z))
 return secs,fns
def _fill_pads(out,link_ui):
 """Space (1.6.8 port): move whole functions from the main .text into the
 free tails of the fixed bank-2 pad sections (first fit, largest first), then
 relink. Location only: no code is changed. Every moved function is checked
 to be inside its pad, every pad against its fixed bound; on overflow the
 last choice for that pad is dropped and the link repeated."""
 import re,tempfile
 bounds=dict(UI_PADS+UI_RETIRED+(UI_BANK1 if os.environ.get('BENTO_M4_MPU_WIDE')=='1' else []));text=(R/'ui.ld').read_text()
 secs,fns=_elf_layout(out);main=main0=secs['.text']
 # all fixed sections from ui.ld (empty ones are absent from the first link)
 declared={m[2]:int(m[1],16) for m in re.finditer(r'\. = (0x[0-9a-f]+); (\.[A-Za-z0-9_]+) :',text)}
 pads={k:(a_,secs.get(k,(a_,0))[1]) for k,a_ in declared.items() if a_ in bounds}
 movable=sorted([f for f in fns if main[0]<=f[1]<main[0]+main[1] and 'OUTLINED' not in f[0] and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*',f[0])],key=lambda f:-f[2])
 plan={k:[] for k in pads};free={k:bounds[v[0]]-v[0]-v[1]-PAD_RESERVE for k,v in pads.items()}
 for name,addr,size in movable:
  need=(size+3)&~3
  for k in sorted(free,key=lambda k:free[k]):
   if free[k]>=need:plan[k].append(name);free[k]-=need;break
 topups=0;refused=set() # (pad, function) pairs lld refused: a moved function can grow (alignment, outlining)
 penalty={k:0 for k in pads} # bytes a pad proved smaller than measured (string/alignment padding once code joins it)
 for attempt in range(60):
  t=text
  for k,names in plan.items():
   if names:t=t.replace(' %s : { '%k,' %s : { '%k+' '.join('*(.text.%s)'%n for n in names)+' ',1)
  fd,ld=tempfile.mkstemp(suffix='.ld',prefix='ui_filled_')
  with os.fdopen(fd,'w') as f:f.write(t)
  try:link_ui(Path(ld))
  except subprocess.CalledProcessError as e:
   # lld refuses an overlapping section: back off exactly the pads it names
   # (R6.18: backing off the "fullest" estimate instead emptied innocent pads);
   # only if it names none, fall back to the fullest pad by estimate
   named={m for m in re.findall(r'section (\.[A-Za-z0-9_]+) (?:file|virtual address|load address) range overlaps',e.stderr or '') if plan.get(m)}
   for k in named or [min((k for k in plan if plan[k]),key=lambda k:free[k])]:
    if os.environ.get('BENTO_PAD_TRACE'):print('pad back-off: %s drops %s'%(k,plan[k][-1]),flush=True)
    refused.add((k,plan[k].pop()));penalty[k]+=8
   continue
  secs,fns=_elf_layout(out);over=[k for k,v in secs.items() if k in plan and v[1]>bounds[v[0]]-v[0]]
  where={n:a for n,a,z in fns}
  # functions in an explicitly named input section (e.g. .text.sls) do not move
  stuck=[(k,n) for k,names in plan.items() for n in names if n in where and not (k in secs and secs[k][0]<=where[n]<secs[k][0]+secs[k][1])]
  if not over and not stuck:
   if os.environ.get('BENTO_PAD_TRACE'):print('pad link ok: '+' '.join('%s=%d/%d'%(k,secs.get(k,(a_,0))[1],bounds[a_]-a_) for k,(a_,_) in pads.items() if plan[k]),flush=True)
   # top-up: refill what a back-off left free, measured on this link
   if topups>=12:break
   topups+=1;placed={n for v in plan.values() for n in v};added=0
   real={k:bounds[a_]-a_-secs.get(k,(a_,0))[1]-PAD_RESERVE-penalty[k] for k,(a_,_) in pads.items()}
   main=secs['.text']
   for name,addr,size in sorted([f for f in fns if f[0] not in placed and main[0]<=f[1]<main[0]+main[1] and 'OUTLINED' not in f[0] and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*',f[0])],key=lambda f:-f[2]):
    need=(size+3)&~3
    for k in sorted(real,key=lambda k:real[k]):
     if real[k]>=need and (k,name) not in refused:
      plan[k].append(name);real[k]-=need;added+=1
      if os.environ.get('BENTO_PAD_TRACE'):print('pad top-up: %s (%d B) -> %s, %d B left'%(name,size,k,real[k]),flush=True)
      break
   if not added:break
   continue
  for k,n in stuck:plan[k].remove(n);refused.add((k,n))
  for k in over:plan[k].pop()
 else:raise SystemExit('pad filler did not converge')
 where={n:a for n,a,z in fns}
 for k,names in plan.items():
  if not names:continue
  lo=secs[k][0];hi=lo+secs[k][1]
  for n in names:assert n not in where or lo<=where[n]<hi,'moved function outside its pad: '+n
 moved=sum(len(v) for v in plan.values())
 print('pad filler: %d functions moved into %d pads; main .text %d -> %d B'%(moved,sum(1 for v in plan.values() if v),main0[1],secs['.text'][1]),flush=True)
def compile_ui(output=None,script=None):
 """Compile only the M4 source, also used by focused non-firmware fixtures."""
 # Space (1.6.8 port): +no-movt loads repeated constants from shared literal
 # pools instead of 8-byte MOVW/MOVT pairs (a function attribute, so the LTO
 # code generation honours it; -mno-movt itself is rejected by zig cc).
 ui_extra=['-DBENTO_SYNCUSSION=1','-flto','-fno-inline-functions','-Xclang','-target-feature','-Xclang','+no-movt','-ffunction-sections',*['-Wl,-u,'+n for n in UI_EXPORTS]] if os.environ.get('BENTO_SYNCUSSION')=='1' else []
 sources=['fx_ui.c','play_mute_ui.c','euclidean.c','live_ui.c','step_lock_ui.c',
          'header_actions.c','melodic_eu.c','lanes_ui.c','bars_ui.c','kick_ui.c',
          'perf_ui.c','synth_draw.c','mod_ui.c','macro_ui.c','melodic_lock_ui.c',
          'seq_nav_ui.c','playground_ui.c','workflow_ui.c','kit_seq_ui.c','inst_bank_ui.c',
          '../drums/drum_models.c','browser_filter_ui.c','ratchet_ui.c','blackbox_ui.c','ui_rt.c','port/xy_ui.c','port/fxv_ui.c']
 out=Path(output) if output else R/'ui.elf'
 def link_ui(ld):
  r=subprocess.run([sys.executable,'-m','ziglang','cc',*ui_extra,'-DBENTO_STOCK_INST=1','-DBENTO_MINIMAL_BANK=1','-DBENTO_UI_SHARED_WEAK=1',*(['-DBENTO_DRUM_DIAG=1'] if os.environ.get('BENTO_DRUM_DIAG')=='1' else []),*([] if _ids.CHORD_EDITOR else ['-DBENTO_NO_CHORD_EDITOR=1']),
   '-target','thumb-freestanding-eabi','-mcpu=cortex_m4','-mfloat-abi=soft','-Oz',
   '-mllvm','-enable-machine-outliner=always','-g','-ffreestanding','-fno-builtin',
   '-fno-stack-protector','-nostdlib','-Wl,--entry=fx_dispatch',
   '-DBENTO_NATIVE_SYMBOLS=1','-Wl,--script='+_native_symbol_script(ld),*[str(R/n) for n in sources],
   *[str(R.parents[1]/'chord_work'/n) for n in (['chords.c','native_insert.c','device.c'] if _ids.CHORD_EDITOR else ['chords.c','device.c'])],
   '-o',str(out)],check=False,**({'env':dict(os.environ,ZIG_VERBOSE_LINK='1'),'stderr':subprocess.PIPE,'text':True} if ui_extra else {}))
  if r.returncode:
   # compiler/linker messages were captured for the link command (the command line itself is omitted)
   if ui_extra:sys.stderr.write('\n'.join(l for l in r.stderr.splitlines() if not l.startswith('ld.lld '))+'\n')
   raise subprocess.CalledProcessError(r.returncode,r.args,stderr=r.stderr if ui_extra else None)
  if ui_extra:_relink_with_outliner(r,out)
 link_ui(script or R/'ui.ld')
 if ui_extra and script is None:_fill_pads(out,link_ui)
 chunks,symbols=elf(out)
 if ui_extra:assert all(n in symbols for n in UI_EXPORTS),'Missing external UI API after LTO'
 return chunks,symbols
def compile():
 global RT_CODE,RT2_CODE,RT_SYMS,MEL_CODE,MEL_SYMS,SEND_CODE,SEND_SYMS,NATIVE_LOCK,ARP_CODE,ARP_SYMS,CONTROLS_CODE,SEQFX_CODE,SEQFX_SYMS
 controls=R.parent/'drums'
 subprocess.run([sys.executable,'-m','ziglang','cc','-target','thumb-freestanding-eabi',
  '-mcpu=cortex_m4','-mfloat-abi=soft','-Oz','-g','-DBENTO_STOCK_INST=1','-ffreestanding','-fno-builtin',
  '-fno-stack-protector','-ffunction-sections','-nostdlib',
  '-Wl,--script='+str(controls/'link.ld'),'-Wl,--entry=controls_dispatch',
  str(controls/'controls.c'),'-o',str(controls/'controls.elf')],check=True)
 CONTROLS_CODE,controls_symbols=elf(controls/'controls.elf')
 assert controls_symbols['controls_dispatch']==0x081b4100
 assert len(CONTROLS_CODE)==2
 # Rebuilt controls retire their old trailing C bodies, not native assets.
 assert all(lo==address and address+len(data)<=hi
            for (address,data),(lo,hi) in zip(CONTROLS_CODE,[(0x081b4100,0x081b4a00),(0x081b5000,0x081b5070)]))
 sys.path.insert(0,str(R.parents[1]/'k16_work/bento_controls'))
 import step_locks
 _,native_lock=step_locks.compile_one('step_lock_audio','cortex_m7',True)
 NATIVE_LOCK=native_lock
 (R/'lock_api.h').write_text('/* Generated from exact K16 APIs. */\n'+
  ''.join('#define LIVE_'+name.upper()+' '+hex(native_lock[name])+'u\n' for name in ['lock_pending','lock_route','lock_queue'])+
  '#define NATIVE_SENDS_BEGIN '+hex(native_lock['sends_begin'])+'u\n'+
  '#define NATIVE_SENDS_END '+hex(native_lock['sends_end'])+'u\n')
 t=R.parent/'track_fx';v=t/'vendor/DaisySP-LGPL'
 common=[sys.executable,'-m','ziglang','c++','-target','thumb-freestanding-eabihf','-mcpu=cortex_m7+fp_armv8d16sp+fpregs+fpregs16+vfp4d16sp','-mfloat-abi=hard','-mfpu=fpv5-sp-d16','-std=c++17','-Os','-flto','-g','-ffreestanding','-fno-builtin','-fno-exceptions','-fno-rtti','-fno-stack-protector','-nostdlib','-nostdlib++','-I'+str(t/'arm_support'),'-I'+str(v),'-I'+str(v/'Utility')]
 mel_cmd=[*common];mel_cmd[mel_cmd.index('-Os')]='-Oz'
 subprocess.run([*mel_cmd,'-Wl,--entry=mel_pending','-Wl,--script='+str(R/'melodic_lock_audio.ld'),str(R/'melodic_lock_audio.cpp'),'-o',str(R/'melodic_lock_audio.elf')],check=True)
 mc,ms=elf(R/'melodic_lock_audio.elf')
 mel_limit=0xd00 if os.environ.get('BENTO_SYNCUSSION')=='1' else 0x1400
 assert len(mc)==1 and mc[0][0]==0x080d4400 and len(mc[0][1])<=mel_limit,'Melodic code overlaps a reserved application region'
 MEL_CODE,MEL_SYMS=mc[0][1],ms
 subprocess.run([*mel_cmd,'-Wl,--entry=mel_send_begin','-Wl,--script='+str(R/'melodic_send_audio.ld'),str(R/'melodic_send_audio.cpp'),'-o',str(R/'melodic_send_audio.elf')],check=True)
 sc,ss=elf(R/'melodic_send_audio.elf');assert len(sc)==1 and sc[0][0]==0x080dac00 and len(sc[0][1])<=0xe00,(len(sc[0][1]),'send helper bounds')
 SEND_CODE,SEND_SYMS=sc[0][1],ss
 # P28 arpeggiator (M7) in the stock-zero cave 080D2500..080D3000 (no other owner).
 arp_extra=['-DBENTO_SYNCUSSION=1'] if os.environ.get('BENTO_SYNCUSSION')=='1' else []
 subprocess.run([*mel_cmd,*arp_extra,'-Wl,--entry=arp_block','-Wl,--script='+str(R/'arp_audio.ld'),str(R/'arp_audio.cpp'),'-o',str(R/'arp_audio.elf')],check=True)
 xc,xs=elf(R/'arp_audio.elf');assert len(xc)==1 and xc[0][0]==0x080d2500 and len(xc[0][1])<=0xb00,(len(xc[0][1]) if xc else 0,'arp bounds')
 ARP_CODE,ARP_SYMS=xc[0][1],xs
 # R6.6 transpose (M7) in the checked zero cave 080D08B0..080D1000.
 subprocess.run([*mel_cmd,'-Wl,--entry=tr_note_pitch','-Wl,--script='+str(R/'seqfx_audio.ld'),str(R/'seqfx_audio.cpp'),'-o',str(R/'seqfx_audio.elf')],check=True)
 qc,qs=elf(R/'seqfx_audio.elf');assert len(qc)==1 and qc[0][0]==0x080d08b0 and len(qc[0][1])<=0x750,(len(qc[0][1]) if qc else 0,'seqfx bounds')
 SEQFX_CODE,SEQFX_SYMS=qc[0][1],qs
 (R/'seqfx_api.h').write_text('/* Generated R6.6 transpose APIs. */\n'+''.join('#define '+n.upper()+' '+hex(qs[n])+'u\n' for n in ['tr_press','tr_release','tr_note_pitch','tr_off_pitch']))
 (R/'arp_api.h').write_text('/* Generated P28 arp APIs. */\n'+''.join('#define '+n.upper()+' '+hex(xs[n])+'u\n' for n in ['arp_press','arp_release','arp_clock','arp_block']))
 (R/'melodic_lock_api.h').write_text('/* Generated exact melodic lock APIs. */\n'+''.join('#define '+n.upper()+' '+hex(ms[n])+'u\n' for n in ['mel_pending','mel_pending_clear']))
 # R6.13 ratchet playback (M7) in the checked stock-zero cave 080CF4C0..080CFFF0
 # (the retired motion layer's gap; no current owner).
 subprocess.run([*mel_cmd,*(['-ffunction-sections'] if RT_FUNCTION_SECTIONS else []),'-Wl,--entry=rt_block','-Wl,--script='+str(R/'ratchet_audio.ld'),str(R/'ratchet_audio.cpp'),'-o',str(R/'ratchet_audio.elf')],check=True)
 rc,rs=elf(R/'ratchet_audio.elf');rc=dict(rc)
 assert set(rc)<=set(lo for lo,hi in RT_SLOTS)|{RT2_CAVE[0]} and RT2_CAVE[0] in rc and RT_SLOTS[0][0] in rc,([(hex(a),len(d)) for a,d in rc.items()],'ratchet sections')
 assert all(lo+len(rc[lo])<=hi for lo,hi in RT_SLOTS if lo in rc) and RT2_CAVE[0]+len(rc[RT2_CAVE[0]])<=RT2_CAVE[1],([(hex(a),len(d)) for a,d in rc.items()],'ratchet bounds')
 RT_CODE=[(lo,rc[lo]) for lo,hi in RT_SLOTS if lo in rc];RT_SYMS=rs;RT2_CODE=rc[RT2_CAVE[0]]
 (R/'ratchet_api.h').write_text('/* Generated R6.16 ratchet APIs. */\n'+''.join('#define '+n.upper()+' '+hex(rs[n])+'u\n' for n in ['rt_live','rt_voice','rt_cond']))
 sources=[R/'fx_audio.cpp',R/'live_audio.cpp',t/'track_fx.cpp',v/'Source/Dynamics/compressor.cpp',v/'Source/Filters/biquad.cpp',t/'arm_support/math_runtime.cpp']
 # Run 17 (1.6.8): the Track FX saturator (TF_SATURATOR) and no host-only record API in the M7 image (TF_NO_RECORD,
 # about 1 KB of the TF2 cave: tf_save/tf_load/tf_get_settings/tf_record_bytes were never called by the firmware).
 sat=['-DTF_SATURATOR=1','-DTF_NO_RECORD=1'] if _ids.BENTO_FW==168 else []
 subprocess.run([*common,*sat,'-Wl,--entry=fx_audio','-Wl,--script='+str(R/'audio.ld'),*map(str,sources),'-o',str(R/'audio.elf')],check=True)
 # Outline repeated M4 instruction sequences; keep every native patch entry
 # and the existing application/padding bounds (no LTO internalization).
 uc,uu=compile_ui()
 ac,aa=elf(R/'audio.elf')
 # W21 adds .pad3 in the overlay's verified zero fill after clean.c and before
 # its fixed 081BD800 trampolines. No executable/RAM/MPU bounds are enlarged.
 global UI_PAD;starts=dict(UI_PADS+UI_RETIRED+UI_BANK1);UI_PAD=[c for c in uc if c[0] in starts];uc=[c for c in uc if c[0] not in starts]
 assert all(len(c)<=starts[a]-a for a,c in UI_PAD)
 assert len(ac)==len(uc)==1 and ac[0][0]==AUDIO and uc[0][0]==UI
 # CH7: UI remains below 081E0000. The K16 image ends at UI_STUB; the M4
 # executable region is unchanged and the extension stays application-only.
 assert AUDIO+len(ac[0][1])<=0x080e0000 and UI+len(uc[0][1])<=0x081e0000
 return ac[0][1],aa,uc[0][1],uu
def build(base):
 if hashlib.sha256(base).hexdigest()!=K16_SHA:raise ValueError('Expected exact K16 base')
 ac,aa,uc,uu=compile();k=Ks(KS_ARCH_ARM,KS_MODE_THUMB);writes=[];image=bytearray(base)
 def asm(s,a):return bytes(k.asm(s,a)[0])
 def put(a,b,why):
  off=a-BASE;assert a>=BASE and a+len(b)<=0x08200000
  hit=[x for x in writes if a<x['address']+x['size'] and x['address']<a+len(b)]
  if hit:raise ValueError('Patch overlap %08X..%08X (%s) with %08X..%08X (%s)'%(a,a+len(b),why[:50],hit[0]['address'],hit[0]['address']+hit[0]['size'],hit[0]['reason'][:50]))
  old=bytes(image[off:off+len(b)]);assert off<=len(image)
  image[off:off+len(b)]=b;writes.append(dict(address=a,size=len(b),original_hex=old.hex(),replacement_hex=b.hex(),reason=why))
 import importlib.util
 kit_spec=importlib.util.spec_from_file_location('kit_seq_input',R/'kit_seq_input.py')
 kit_input=importlib.util.module_from_spec(kit_spec);kit_spec.loader.exec_module(kit_input)
 for address,data,expected,why in kit_input.writes_for(base):
  assert base[address-BASE:address-BASE+len(expected)]==expected
  put(address,data,why)
 # exp6 (owner, exp5 photo: the Projects view showed "P168 exp5-cont-15"): the native version text is
 # snprintf(buf,64,"%s-cont-%d",version,controller version). Its one format pointer now points at the "%s"
 # that ends the native string "SF2: failed to open %s", so only the version (our label) is shown. Found by
 # content in either version; one guarded, reversible literal word; the controller version argument is ignored.
 fmt=base.find(b'%s-cont-%d\0');lit=struct.pack('<I',BASE+fmt);plain=base.find(b'SF2: failed to open %s\0')
 assert fmt>0 and plain>0 and base.count(lit)==1 and base.count(b'%s-cont-%d\0')==1,'version format'
 site=BASE+base.index(lit);assert site%4==0
 put(site,struct.pack('<I',BASE+plain+len(b'SF2: failed to open ')),'exp6 native version text without "-cont-N" (label only)')
 # Replace only the existing K16 synth cave and its existing render adapter.
 for address,data in CONTROLS_CODE:
  put(address,data,'Current M4 hold controls in existing K16 controls/mixer bodies')
 import importlib.util
 spec=importlib.util.spec_from_file_location('eu4_kick',R.parent/'drums/kick_build.py')
 dk=importlib.util.module_from_spec(spec);spec.loader.exec_module(dk)
 dk.RT_VOICE=RT_SYMS['rt_voice'] # R6.16c mono roll: safe hook (no-op unless a valid request of an armed ratchet is pending)
 for address,data,expected,why in dk.writes_for(base,0):
  put(address,data,'EU10 same synth formulas, block constants and LTO: '+why)
 integer_prefix='push.w {r0-r12,lr}; mrs r0,APSR; push {r0,r1}; '
 integer_restore='pop {r0,r1}; msr APSR_nzcvq,r0; pop.w {r0-r12,lr}; '
 prefix=integer_prefix+'vpush {d0-d7}; '
 restore='vpop {d0-d7}; pop {r0,r1}; msr APSR_nzcvq,r0; pop.w {r0-r12,lr}; '
 aw=bytearray()
 def ab(s):
  while len(aw)%4:aw.append(0)
  a=0x080dc000+len(aw);aw.extend(asm(s,a));return a
 a=ab(prefix+'mov r0,r9; mov r1,r4; mov r2,r10; mov r3,r5; bl '+hex(aa['fx_audio'])+'; '+restore+'vldr s15,[r5]; b.w 0x080a0514')
 assert base[0x080a0510-BASE:0x080a0514-BASE]==bytes.fromhex('d5ed007a')
 put(0x080a0510,asm('b.w '+hex(a),0x080a0510),'TF2 per-track scratch after native Level, before pan and sends')
 # Instruments consume their native queues before the mixer; all queues are
 # cleared at block end. Schedule held-pad notes before the graph, not in FX.
 a=ab(prefix+'add.w r0,r8,#8; ldrb r1,[r0,#0x38]; cbz r1,arp_free; bl '+hex(ARP_SYMS['arp_clock'])+'; arp_free: ldr r0,[r5,#0x34]; movs r1,#0; bl '+hex(ARP_SYMS['arp_block'])+'; '+restore+'b.w 0x080654a0')
 assert base[0x08057d26-BASE:0x08057d2a-BASE]==asm('bl 0x080654a0',0x08057d26)
 put(0x08057d26,asm('bl '+hex(a),0x08057d26),'Arp once per audio block before native graph consumers; chain unchanged graph traversal')
 # Startup initialization remains separate for both core owners.
 a=ab(integer_prefix+'ldr r0,=0x24040000; movs r1,#0; movw r2,#1296; zero: str r1,[r0],#4; subs r2,#1; bne zero; ldr r0,=0x240416c0; movw r2,#208; meta: str r1,[r0],#4; subs r2,#1; bne meta; dsb; '+(XY.BOOT if XY else '')+integer_restore+'b.w 0x080d0800')
 put(0x080404b6,asm('b.w '+hex(a),0x080404b6),'Initialize new M7-owned FX memory, then original K16 startup')
 a=ab(prefix+'sub sp,#8; ldr r0,[sp,#136]; str r0,[sp]; ldr r0,[sp,#80]; ldr r1,[sp,#84]; ldr r2,[sp,#88]; ldr r3,[sp,#92]; bl '+hex(aa['live_render'])+'; add sp,#8; '+restore+'push.w {r4-r11,lr}; b.w 0x08060824')
 put(0x08060820,asm('b.w '+hex(a),0x08060820),'EU10 native timed-note renderer entry')
 a=ab(prefix+'mov r0,r8; ldrh.w r1,[sp,#170]; ldrh.w r2,[sp,#184]; bl '+hex(aa['live_skip'])+'; cmp r0,#0; bne skip; mov r0,r8; ldrb.w r1,[sp,#169]; bl '+hex(aa['note_condition'])+'; cmp r0,#1; beq play; cmp r0,#0; beq skip; '+restore+'b.w 0x080d2000; play: '+restore+'movs r3,#0; b.w 0x08060b68; skip: '+restore+'b.w 0x080609e2')
 put(0x08060b64,asm('b.w '+hex(a),0x08060b64),'EU10 suppress only native hits for generator-controlled pads; exp5 note condition 1ST/!1ST/PRE/!PRE (rt_cond); chain conditions')
 a=ab(prefix+'ldr r0,[sp,#72]; bl '+hex(aa['live_restart'])+'; '+restore+'b.w 0x080d2100')
 put(0x08061740,asm('b.w '+hex(a),0x08061740),'EU10 restart on launches, preserve phase on normal loop; chain condition counter')
 # Resolve conditional payload only after the native note condition passed.
 # K16 adapter receives its accepted note word at original SP+60.
 old_native=0x080d3000
 a=ab(prefix+'ldr r4,[sp,#188]; mov r0,r8; mov r1,r4; bl '+hex(aa['locks_native_filter'])+'; str r0,[sp,#188]; mov r0,r8; mov r1,r4; add r2,sp,#72; bl '+hex(RT_SYMS['rt_note'])+'; mov r0,r8; ldr r1,[sp,#132]; ldrh.w r2,[sp,#170]; ldr r3,[sp,#188]; bl '+hex(MEL_SYMS['mel_pending'])+'; '+restore+'b.w '+hex(old_native))
 put(0x08060b9a,asm('b.w '+hex(a),0x08060b9a),'EU10 conditional lock payload on accepted native hits; R6.13 ratchet arming')
 # R6.13: the per-sequence renderer's only caller; later ratchet hits are played
 # after the native notes of the same segment, on their exact frames.
 assert base[0x080601e8-BASE:0x080601ec-BASE]==asm('bl 0x08060820',0x080601e8)
 a=ab('push {r0,r1,r2,r3,r4,lr}; ldr r4,[sp,#24]; sub sp,#8; str r4,[sp]; bl 0x08060820; str r4,[sp]; ldr r0,[sp,#8]; ldr r1,[sp,#12]; ldr r2,[sp,#16]; ldr r3,[sp,#20]; bl '+hex(RT_SYMS['rt_block'])+'; add sp,#8; pop {r0,r1,r2,r3,r4,pc}')
 put(0x080601e8,asm('bl '+hex(a),0x080601e8),'R6.13 ratchet hits after each native sequencer segment')
 # CH9 (owner): the per-track meter measured the raw track signal plus the fader
 # level (080A0566 reads r6, 080A055C/05C0/05E0 load the level offset), so Track
 # FX (clipper/compressor/EQ) never showed. Measure r4 instead: after Level and
 # Track FX (the TF2 hook at 080A0510), before pan/sends; no offset.
 for site_a,old,new,why in [(0x080a055c,'95ed1c8a0023','movs r3,#0; vmov s16,r3','meter offset 0 (post-level buffer)'),
                            (0x080a0566,'3046','mov r0,r4','meter the post-level, post-Track-FX buffer'),
                            (0x080a05c0,'95ed0a8a','b 0x080a055c; nop','other track type: same zero offset'),
                            (0x080a05e0,'95ed108a','b 0x080a055c; nop','other track type: same zero offset')]:
  assert base[site_a-BASE:site_a-BASE+len(old)//2].hex()==old,hex(site_a)
  mb=asm(new,site_a);assert len(mb)==len(old)//2,(hex(site_a),len(mb));put(site_a,mb,'CH9 meter after Track FX: '+why)
 # CH6 chord pad audition: the native keyboard-pad press/release posts in the
 # pad module (08084760 press, 08083FE0 release) call chord_press/chord_release,
 # which post the whole chord while M4 chord mode is active, else the original.
 for site_a,fn,args,why in [(0x08084918,'chord_press','mov r2,r4; movs r3,#0','track press'),(0x0808494e,'chord_press','mov r2,r4; movs r3,#1','layer press'),(0x0808414a,'chord_release','movs r2,#0','track release'),(0x08084180,'chord_release','movs r2,#1','layer release')]:
  assert base[site_a-BASE:site_a-BASE+4]==asm('bl 0x0809eca0',site_a),hex(site_a)
  # R6.6: transpose sees every keyboard pad first (tr_press/tr_release return 1 = kept).
  tr='tr_press' if fn=='chord_press' else 'tr_release'
  a=ab(args+'; push {r0-r3,r4,lr}; bl '+hex(SEQFX_SYMS[tr])+'; cmp r0,#0; pop {r0-r3,r4,lr}; it ne; bxne lr; b.w '+hex(aa[fn]))
  put(site_a,asm('bl '+hex(a),site_a),'CH6 chord pad audition (R6.6 via transpose): '+why)
 # CH11 Mod Matrix: the sampler's 0x3F route command (0808F38E) offers synth
 # destinations to kick_route first, which keeps them in the root's own list.
 assert base[0x0808f38e-BASE:0x0808f392-BASE]==asm('bl 0x080925e0',0x0808f38e)
 a=ab('push {r0,r1,r2,lr}; bl '+hex(dk.SYMS['kick_route'])+'; cmp r0,#0; pop {r0,r1,r2,lr}; beq native; bx lr; native: b.w 0x080925e0')
 put(0x0808f38e,asm('bl '+hex(a),0x0808f38e),'CH11 synth destinations in the native route command')
 # A1 Analog Wavetable: the Wavetable root's per-voice render (vtable 080AC798
 # slot 18) records voice and track mode; the WT oscillator class (080AC3E4
 # slot 0) renders analog WT1/WT2 and leaves every other oscillator native.
 for slot,old,fn,why in [(0x080ac7e0,0x0809be81,'kick_analog_enter','Wavetable voice: note analog mode'),(0x080ac3e4,0x08081361,'kick_analog_osc','WT oscillator: analog render')]:
  assert struct.unpack_from('<I',base,slot-BASE)[0]==old,hex(slot)
  if fn=='kick_analog_enter':a=ab('push {r0-r3,r12,lr}; bl '+hex(dk.SYMS[fn])+'; pop {r0-r3,r12,lr}; b.w '+hex(old&~1))
  else:a=ab('push {r0-r3,r4,lr}; bl '+hex(dk.SYMS[fn])+'; cmp r0,#0; pop {r0-r3,r4,lr}; beq native; bx lr; native: b.w '+hex(old&~1))
  put(slot,struct.pack('<I',a|1),'A1 '+why)
 # P1 fixed velocity: the pad module's press call (08085540 -> 08084760) lets
 # perf_press adjust the record's pressure first.
 assert base[0x080857d6-BASE:0x080857da-BASE]==asm('bl 0x08084760',0x080857d6)
 a=ab('push {r0-r3,r12,lr}; mov r0,r1; bl '+hex(aa['perf_press'])+'; pop {r0-r3,r12,lr}; b.w 0x08084760')
 put(0x080857d6,asm('bl '+hex(a),0x080857d6),'P1 fixed velocity before the native pad press')
 # P4/P6 Analog oscillator display: the Wavetable pane class (081B3A18) tick [0] and
 # paint [1] go through analog_wave_tick/paint, which call the native ones.
 for slot,old,fn in [(0x081b3a18,0x081822a5,'analog_wave_tick'),(0x081b3a1c,0x08182315,'analog_wave_paint')]:
  assert struct.unpack_from('<I',base,slot-BASE)[0]==old,hex(slot)
  put(slot,struct.pack('<I',uu[fn]|1),'P4 Analog wave pane: '+fn)
 # P8 mod mode: the synth page view class (0819E894, Wavetable/Granular) tick [0]
 # and event [12] go through mod_view_tick/mod_view_event, which call the native ones.
 for slot,old,fn in [(0x0819e894,0x0815d7d1,'mod_view_tick'),(0x0819e8c4,0x0815f149,'mod_view_event')]:
  assert struct.unpack_from('<I',base,slot-BASE)[0]==old,hex(slot)
  put(slot,struct.pack('<I',uu[fn]|1),'P8 mod mode: '+fn)
 # P7: the P5 header chord symbol is removed (owner: overlaps the counter).
 # P6 Drum Synth action from the pad page view too (handler 0814888C).
 assert struct.unpack_from('<I',base,0x0819dc50-BASE)[0]==0x0814888d
 put(0x0819dc50,struct.pack('<I',uu['drum_view_event']|1),'P6 Drum Synth action on the pad page view')
 # PROJ is navigation, never an audio transport or pad modifier.
 mask=asm('and r0,r0,#0x3500',0)
 region=base[0x080d0000-BASE:0x080d0800-BASE]
 assert region.count(mask)==1,'exact inherited input modifier mask'
 address=0x080d0000+region.index(mask)
 put(address,asm('and r0,r0,#0x3400',address),'Workflow: remove PROJ from pad modifiers; preserve MIXER/TRACKS/LAUNCH')
 # P26 (owner: "hold LAUNCH: the pads don't work"; wanted: the pads play/select the
 # clip, or the empty slot, inside the white rectangle on their track = the native
 # Launch page's own pad function). K16's input hook turned LAUNCH+pad into its
 # stop/start request; LAUNCH now passes the pad through to the native page.
 assert base[0x080d0058-BASE:0x080d005e-BASE]==bytes.fromhex('b0f5805f18d0') # cmp.w r0,#0x1000 (LAUNCH); beq launch
 put(0x080d005c,bytes.fromhex('5ad0'),'P26 LAUNCH hold: pads go to the native Launch page (K16 input passthrough)')
 # Reuse K16's owned-pad mask through pressure and either release order.
 # This branch runs only for fresh presses; notes held before PLAY keep their
 # native note-off. Receiver+8C8 is the native transport command owner.
 play_input=0x080d0200
 pi=asm('''
 add.w r0,r11,#0x1000
 ldrh r0,[r0,#0x338]
 cmp r0,#1
 bne ordinary
 ldr r1,[r11,#0x8c8]
 cbz r1,ordinary
 ldrb r1,[r1,#0x40]
 cbz r1,ordinary
 add.w r0,r8,#16
 ldrb r6,[r0,r7]
 cmp r6,#15
 bhi ordinary
 orr.w r9,r9,r10
 strh r9,[r8,#4]
 ldr r0,=0x2401bd3c
 ldr r0,[r0]
 add.w r1,r0,#0x2000
 ldr r2,[r1,#0x1a0]
 ldr r3,[r1,#0x180]
 subs r2,r2,r3
 cmp r2,#224
 bhs full
 movs r1,#254
 str r1,[sp]
 ldr r1,=0x314d5442
 str r1,[sp,#4]
 ldr r1,=0x31544d50
 str r1,[sp,#8]
 str r6,[sp,#12]
 movs r1,#10
 str r1,[sp,#16]
 ldr r1,=0x31525442
 str r1,[sp,#20]
 mov r1,sp
 bl 0x08082220
 b.w 0x080d0106
 full:
 ldr r0,[r8,#8]
 adds r0,#1
 str r0,[r8,#8]
 b.w 0x080d0106
 ordinary:
 add.w r0,r11,#0x1000
 ldrh r0,[r0,#0x338]
 b.w 0x080d004a
 ''',play_input)
 assert len(pi)<=0x100 and base[play_input-BASE:play_input-BASE+len(pi)]==bytes(len(pi)) # R6.14: ends before play_bank
 put(play_input,pi,'W21 PLAY-held running transport: silent full-pad mute requests; unchanged K16 ownership/queue guards')
 assert base[0x080d0042-BASE:0x080d004a-BASE]==asm('add.w r0,r11,#0x1000; ldrh r0,[r0,#0x338]',0x080d0042)
 put(0x080d0042,asm('b.w '+hex(play_input)+'; nop; nop',0x080d0042),'W21 fresh pad modifier branch')
 # M7 owns byte +13 of the existing K16 state. Publish only changes, before
 # pad processing, so button-only presses and stop/release restore the LEDs.
 play_bank=0x080d0300
 pb=asm('''
 push.w {r0-r12,lr}
 sub sp,#24
 mov r11,r4
 ldr r8,=0x24048ca0
 ldr r0,[r8]
 ldr r1,=0x31534d42
 cmp r0,r1
 bne done
 movs r6,#0
 ldrb r0,[r8,#12]
 cmp r0,#1
 bne state
 add.w r0,r11,#0x1000
 ldrh r0,[r0,#0x338]
 cmp r0,#1
 bne state
 ldr r0,[r11,#0x8c8]
 cbz r0,state
 ldrb r0,[r0,#0x40]
 cbz r0,state
 movs r6,#1
 state:
 ldrb r0,[r8,#13]
 cmp r0,r6
 beq done
 ldr r0,=0x2401bd3c
 ldr r0,[r0]
 add.w r1,r0,#0x2000
 ldr r2,[r1,#0x1a0]
 ldr r3,[r1,#0x180]
 subs r2,r2,r3
 cmp r2,#224
 bhs full
 movs r1,#254
 str r1,[sp]
 ldr r1,=0x314d5442
 str r1,[sp,#4]
 ldr r1,=0x31544d50
 str r1,[sp,#8]
 str r6,[sp,#12]
 movs r1,#11
 str r1,[sp,#16]
 ldr r1,=0x31525442
 str r1,[sp,#20]
 mov r1,sp
 bl 0x08082220
 strb r6,[r8,#13]
 b done
 full:
 ldr r0,[r8,#8]
 adds r0,#1
 str r0,[r8,#8]
 done:
 add sp,#24
 pop.w {r0-r12,lr}
 movw r7,#0x141a
 bx lr
 ''',play_bank)
 assert len(pb)<=0x200 and base[play_bank-BASE:play_bank-BASE+len(pb)]==bytes(len(pb)) # R6.14: ends before the bank-1 M4 cave at 080D0510
 put(play_bank,pb,'W22 PLAY-bank transitions via checked queue; M7-only K16 state byte +13')
 assert base[0x0808d0dc-BASE:0x0808d0e0-BASE]==asm('movw r7,#0x141a',0x0808d0dc)
 put(0x0808d0dc,asm('bl '+hex(play_bank),0x0808d0dc),'W22 publish PLAY-bank transitions once per validated raw input packet')
 # P14 melodic locks: separately guarded zero caves, retaining K16 code.
 mw=bytearray()
 def mab(code):
  while len(mw)%4:mw.append(0)
  address=0x080dba00+len(mw);mw.extend(asm(code,address));return address
 # Tag only the primary queue of an owner enabled by the melodic editor.
 a=mab(integer_prefix+'ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(NATIVE_LOCK['lock_queue'])+'; ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(MEL_SYMS['mel_queue'])+'; '+integer_restore+'ldr.w r3,[r0,#0x600]; b.w 0x08065604')
 put(0x08065600,asm('b.w '+hex(a),0x08065600),'P14 queue p-lock payload; chain exact legacy drum queue adapter')
 # Clear after native accepted-note emitter returns.
 assert base[0x08060b9e-BASE:0x08060ba2-BASE]==asm('ldr.w r3,[r9,#0x6c0]',0x08060b9e)
 a=mab(prefix+'bl '+hex(MEL_SYMS['mel_pending_clear'])+'; '+restore+'ldr.w r3,[r9,#0x6c0]; b.w 0x08060ba2')
 put(0x08060b9e,asm('b.w '+hex(a),0x08060b9e),'P14 clear melodic pending word after accepted hit')
 a=mab(prefix+'ldr r0,[sp,#72]; ldr r1,[sp,#76]; bl '+hex(MEL_SYMS['mel_note'])+'; '+restore+'ldr r3,[r0]; push.w {r4-r10,lr}; b.w 0x0807ebe6')
 assert base[0x0807ebe0-BASE:0x0807ebe6-BASE]==asm('ldr r3,[r0]; push.w {r4-r10,lr}',0x0807ebe0)
 put(0x0807ebe0,asm('b.w '+hex(a)+'; nop',0x0807ebe0),'P14 generic melodic note capture')
 a=mab(prefix+'mov r0,r7; mov r1,r4; bl '+hex(MEL_SYMS['mel_attach'])+'; '+restore+'mov r0,r7; bl 0x0807e020; b.w 0x0807c0fc')
 assert base[0x0807c0f6-BASE:0x0807c0fc-BASE]==asm('mov r0,r7; bl 0x0807e020',0x0807c0f6)
 put(0x0807c0f6,asm('b.w '+hex(a)+'; nop',0x0807c0f6),'P14 capture locks on initialized native melodic voice')
 a=mab(prefix+'ldr r0,[sp,#72]; ldr r1,[sp,#76]; bl '+hex(MEL_SYMS['mel_context'])+'; ldr r0,[sp,#72]; ldr r1,[sp,#76]; ldr r2,[sp,#140]; bl '+hex(SEND_SYMS['mel_send_voice'])+'; str r0,[sp,#140]; '+restore+'b.w 0x0807b000')
 assert base[0x0807a80e-BASE:0x0807a812-BASE]==asm('bl 0x0807b000',0x0807a80e)
 put(0x0807a80e,asm('bl '+hex(a),0x0807a80e),'P14 bind per-voice filter evaluation context')
 a=mab(prefix+'bl '+hex(SEND_SYMS['mel_send_voice_end'])+'; bl '+hex(MEL_SYMS['mel_context_clear'])+'; '+restore+'b.w 0x0807a7e0')
 put(0x0807a812,asm('b.w '+hex(a)+'; nop',0x0807a812),'P14 leave per-voice evaluation context')
 a=mab(prefix+'mov r0,r4; mov r1,r7; bl '+hex(MEL_SYMS['mel_level'])+'; '+restore+'ldrb.w r3,[r5,#0x161]; b.w 0x0807b1a8')
 assert base[0x0807b1a4-BASE:0x0807b1a8-BASE]==asm('ldrb.w r3,[r5,#0x161]',0x0807b1a4)
 put(0x0807b1a4,asm('b.w '+hex(a),0x0807b1a4),'P14 voice gain before native pan/mix')
 evsave='push.w {r0-r3,r12,lr}; vpush {d0-d7}; '
 evrestore='vpop {d0-d7}; pop.w {r0-r3,r12,lr}; '
 a=mab('ldr r1,=0x24041fc0; ldr r2,[r1]; ldr r3,=0x324c5545; cmp r2,r3; bne legacy; ldr r1,[r1,#4]; cbz r1,legacy; ldr r1,[r1,#16]; cbz r1,legacy; ldr r2,[r1,#80]; cbz r2,legacy; subs r3,r0,r2; movw r2,#0x5c4; cmp r3,r2; beq check; adds r2,#0x48; cmp r3,r2; beq check; adds r2,#0x48; cmp r3,r2; beq check; adds r2,#0x48; cmp r3,r2; beq check; adds r2,#0x48; cmp r3,r2; bne legacy; check: '+evsave+'bl '+hex(MEL_SYMS['mel_evaluate'])+'; cmp r0,#0; '+evrestore+'beq legacy; vldr s0,[r0,#0x3c]; bx lr; legacy: b.w 0x080d1100')
 put(0x0809fd80,asm('b.w '+hex(a),0x0809fd80),'P14 fast per-voice filter lock guard; chain unchanged drum evaluator')
 # P15: phase-local envelope evaluation also catches note-off outside render.
 for address,kind in [(0x0808773a,7),(0x08087aae,9)]:
  assert base[address-BASE:address-BASE+4]==asm('bl 0x0809fd80',address)
  a=mab(evsave+'movs r1,#'+str(kind)+'; bl '+hex(MEL_SYMS['mel_envelope'])+'; cmp r0,#0; '+evrestore+'beq native; vldr s0,[r0,#0x3c]; bx lr; native: b.w 0x0809fd80')
  put(address,asm('bl '+hex(a),address),'P15 Env 1 phase entry: note-owned decay/release')
 # Root rendering begins only after incoming note events have been applied.
 address=0x0807a7c8
 assert base[address-BASE:address-BASE+4]==asm('mov sl,r5; ldr r7,[sp,#0x20]',address)
 a=mab(prefix+'mov r0,r4; mov r1,r8; bl '+hex(SEND_SYMS['motion_send_begin'])+'; mov r0,r4; mov r1,r8; bl '+hex(SEND_SYMS['mel_send_begin'])+'; '+restore+'mov sl,r5; ldr r7,[sp,#0x20]; b.w 0x0807a7cc')
 put(address,asm('b.w '+hex(a),address),'P15 begin isolated note sends after note events')
 address=0x0807ab60
 assert base[address-BASE:address-BASE+4]==asm('ldr r3,[r4,#0x3c]; cbz r3,0x0807ab6c',address)
 a=mab(prefix+'mov r0,r4; bl '+hex(SEND_SYMS['mel_send_end'])+'; '+restore+'ldr r3,[r4,#0x3c]; cmp r3,#0; bne native; b.w 0x0807ab6c; native: b.w 0x0807ab64')
 put(address,asm('b.w '+hex(a),address),'P15 publish isolated send submixes after all voices')
 for address,fn,args,native in [(0x080a050c,'mel_send_prepare','mov r0,r5; mov r1,r6',0x0805bc40),(0x080a0526,'mel_send_duck','mov r0,r5',0x080635e0)]:
  assert base[address-BASE:address-BASE+4]==asm('bl '+hex(native),address)
  extra=(args+'; bl '+hex(SEND_SYMS['motion_send_prepare'])+'; ') if fn=='mel_send_prepare' else ''
  a=mab(prefix+extra+args+'; bl '+hex(SEND_SYMS[fn])+'; '+restore+'b.w '+hex(native))
  put(address,asm('bl '+hex(a),address),'P15 snapshot native track gain/duck before state advances')
 for address in [0x080a0532,0x080a053e]:
  assert base[address-BASE:address-BASE+4]==asm('bl 0x0805bc40',address)
  a=mab('push {r3,lr}; mov r3,r5; bl '+hex(SEND_SYMS['motion_send_mix'])+'; pop {r3,pc}')
  put(address,asm('bl '+hex(a),address),'P15 per-note send bus mix; native fallback without send locks')
 assert base[0x0807aac0-BASE:0x0807aac4-BASE]==asm('bl 0x0807c120',0x0807aac0)
 put(0x0807aac0,asm('bl '+hex(SEND_SYMS['motion_send_dispatch']),0x0807aac0),'Native A-D send routes on generic instrument tracks')
 for native,fn,count in [('sends_begin','motion_pad_start',1),('sends_end','motion_pad_finish',2)]:
  sites=[address for address in range(0x080d3000,0x080d33bc,2)
         if base[address-BASE:address-BASE+4]==asm('bl '+hex(NATIVE_LOCK[native]),address)]
  assert len(sites)==count,(native,sites)
  for address in sites:put(address,asm('bl '+hex(SEND_SYMS[fn]),address),'Pad Send Motion outside existing step-lock override')
 assert len(mw)<=0x600 and base[0x080dba00-BASE:0x080dba00-BASE+len(mw)]==bytes(len(mw)),len(mw)
 assert 0x080dba00+len(mw)<=BANK1B-0x10,('P14 adapters reach the bank-1 M4 cave',len(mw))
 assert base[0x080dac00-BASE:0x080dac00-BASE+len(SEND_CODE)]==bytes(len(SEND_CODE))
 put(0x080dac00,SEND_CODE,'P15 note send routing in checked application cave')
 aa.update(SEND_SYMS)

 # MPU A/B (owner 8 Nov): opt-in widening of the stock M4 MPU region 1 from
 # 08100000/1 MB to 08000000/2 MB so flash bank 1 becomes readable/executable
 # for the M4 (needed to place M4 code in the verified bank-1 zero caves). Only
 # the region 1 base and size immediates in the native setup 08114D74 change.
 if os.environ.get('BENTO_M4_MPU_WIDE')=='1':
  for at,old,new,why in [(0x08114dbe,'mov.w r3,#0x8100000','mov.w r3,#0x8000000','base 08100000 -> 08000000'),
                         (0x08114dc4,'movs r3,#0x13','movs r3,#0x14','size 1 MB -> 2 MB')]:
   o=asm(old,at);n=asm(new,at);assert len(o)==len(n) and base[at-BASE:at-BASE+len(o)]==o,hex(at)
   put(at,n,'MPU A/B: M4 MPU region 1 '+why)
 # R6.6 transpose: code in a checked zero run; the native note-on / note-off
 # entries branch to adapters that adjust the pitch argument (r1) and run the
 # displaced 8-byte position-independent prologues.
 assert base[0x080d08ae-BASE:0x080d1000-BASE]==bytes(0x080d1000-0x080d08ae),'R6.6 seqfx cave must be stock zero'
 put(0x080d08b0,SEQFX_CODE,'R6.6 transpose (M7) in checked zero cave 080D08B0..080D1000')
 for entry,fn,prologue,back in [(0x0805f8e0,'tr_note_pitch','push.w {r4,r5,r6,r7,r8,r9,r10,lr}; add.w r5,r0,#0x8000',0x0805f8e8),
                                (0x0805fe00,'tr_off_pitch','push.w {r4,r5,r6,r7,r8,lr}; add.w r5,r0,#0x8000',0x0805fe08)]:
  old8=asm(prologue,entry);assert len(old8)==8 and base[entry-BASE:entry-BASE+8]==old8,hex(entry)
  a=ab('push {r0-r3,r12,lr}; bl '+hex(SEQFX_SYMS[fn])+'; str r0,[sp,#4]; pop {r0-r3,r12,lr}; '+prologue+'; b.w '+hex(back))
  put(entry,asm('b.w '+hex(a),entry)+asm('nop; nop',entry+4),'R6.6 transpose: '+fn+' at the native note entry')
# R6.17 trigger conditions: the shared condition label table 081B6000 (K16 T2:
 # 135 pointers, then the A:B labels and the T2 marker, zeros to 081B6300 where
 # .stepstrings starts) is rebuilt in place with 139 pointers: native labels
 # 0..99 unchanged, A:B 100..134 unchanged text, + 1ST !1ST PRE !PRE (135..138).
 # The native probability list keeps its count (135), so native steps can't pick them.
 T,TEND=0x081b6000,0x081b6300;old=bytes(base[T-BASE:TEND-BASE]);ptrs=list(struct.unpack_from('<135I',old,0))
 def cstr(a):
  o=a-BASE;return bytes(base[o:base.index(b'\0',o)])
 assert all(T+135*4<=q<TEND for q in ptrs[100:]) and ptrs[100]==T+135*4,'T2 label table layout changed'
 tail=old[max(ptrs[100:])-T:].rstrip(b'\0');marker=tail[tail.index(b'\0')+1:]+b'\0'
 assert marker.startswith(b'BENTO_MOD:trigger-conditions'),marker
 names=[cstr(q) for q in ptrs[100:]]+[b'1ST',b'!1ST',b'PRE',b'!PRE']
 blob=b'';at=[]
 for nm in names:at.append(T+139*4+len(blob));blob+=nm+b'\0'
 # P168 exp5 (owner, 12 Nov): the table is in PICKER order (step_lock_shared.h cond_pos/cond_code):
 # 100..108 A:B up to 4:4, 109..112 1ST !1ST PRE !PRE (offered: 113), 113..138 the older A:B 5:5..8:8
 # (shown when a note has one, never offered). Stored codes are unchanged; every picker converts.
 new=ptrs[:100]+at[0:9]+at[35:39]+at[9:35]
 table=struct.pack('<139I',*new)+blob+marker
 assert T+len(table)<=TEND-4,('R6.17 label table overflows .stepstrings',len(table))
 table+=bytes(TEND-T-len(table))
 put(T,table,'R6.17 condition labels + 1ST !1ST PRE !PRE (139 entries, rebuilt in place)')
 # exp5: the native note editors (K16 T2 helpers) convert between the stored note byte and the list
 # position; new helpers in picker order replace the K16 branch targets, and the native list offers 113.
 def note_helper(src,site,old_hex,why):
  assert bytes(base[site-BASE:site-BASE+4])!=bytes.fromhex(old_hex),hex(site)   # K16 already branches here
  a=ab(src);put(site,asm('b.w '+hex(a),site),'exp5 note condition picker order: '+why)
 def show(store,back):
  return f'cmp r3,#100; blo dec; cmp r3,#109; blo store; cmp r3,#135; blo legacy; cmp r3,#138; bls new; movs r3,#99; b store; new: subs r3,#26; b store; legacy: adds r3,#4; b store; dec: subs r3,#1; store: str r3,[{store}]; b.w {back}'
 note_helper(show('r6','0x08159b84'),0x08159b80,'013b3360','piano display')
 note_helper(show('r1','0x0815c3d6'),0x0815c3d2,'013b0b60','drum display')
 note_helper('cmp r1,#138; bhi unknown; cmp r1,#113; bhs legacy; cmp r1,#109; bhs new; cmp r1,#100; bhs direct; cmp r1,#99; beq unknown; adds r6,r1,#1; b done; legacy: subs r6,r1,#4; b done; new: add.w r6,r1,#26; b done; direct: mov r6,r1; b done; unknown: movs r6,#0; done: b.w 0x0815c8be',0x0815c8b4,'63291abf','drum set')
 ref='cbz r3,always; cmp r3,#100; blo done; cmp r3,#109; blo ab; cmp r3,#135; blo legacy; cmp r3,#138; bhi always; subs r3,#25; b done; legacy: adds r3,#5; b done; ab: adds r3,#1; b done; always: movs r3,#100; done: '
 note_helper('ldrb.w r3,[sp,#0x25]; '+ref+'b.w 0x08158f26',0x08158f1c,'9df82530','piano reference')
 note_helper('ldrb.w r3,[sp,#0x19]; ldr r2,[sp,#0x84]; cbz r2,store; '+ref.replace('done','ok')+'adds r3,r3,r2; cmp r3,#1; bge minok; movs r3,#1; minok: cmp r3,#113; ble maxok; movs r3,#113; maxok: cmp r3,#100; beq zero; blo store; cmp r3,#109; bls dec; adds r3,#25; b store; dec: subs r3,#1; b store; zero: movs r3,#0; store: strb.w r3,[sp,#0x31]; b.w 0x08158aac',0x08158a7c,'9df81930','piano relative edit')
 assert bytes(base[0x08165d40-BASE:0x08165d40+4-BASE])==asm('movs r3,#135; str r3,[sp]',0x08165d40),'T2 list count'
 put(0x08165d40,asm('movs r3,#113; str r3,[sp]',0x08165d40),'exp5 native note condition list offers 113 entries (A:B to 4:4, 1ST..!PRE)')
 if len(RT_SLOTS)==1:  # 1.6.1: the retired motion gap 080CF4A0..080D0000
  assert base[RT_RUN-BASE:0x080d0000-BASE]==bytes(0x080d0000-RT_RUN) and bytes(image[RT_RUN-BASE:0x080d0000-BASE])==bytes(0x080d0000-RT_RUN),'R6.13 ratchet cave must be stock zero and unwritten'
  put(RT_CAVE[0],RT_CODE[0][1],'R6.13 ratchet playback (M7) in checked zero cave 080CF4C0..080CFFF0')
 else:
  for lo,code in RT_CODE:
   hi=dict(RT_SLOTS)[lo]
   assert base[lo-16-BASE:hi+16-BASE]==bytes(hi-lo+32) and bytes(image[lo-16-BASE:hi+16-BASE])==bytes(hi-lo+32),'ratchet slot %08X must be stock zero and unwritten'%lo
   put(lo,code,'R6.13 ratchet playback (M7) in checked zero slot %08X..%08X'%(lo,hi))
 assert base[RT2_CAVE[0]-16-BASE:RT2_CAVE[1]+16-BASE]==bytes(RT2_CAVE[1]-RT2_CAVE[0]+32) and bytes(image[RT2_CAVE[0]-16-BASE:RT2_CAVE[1]+16-BASE])==bytes(RT2_CAVE[1]-RT2_CAVE[0]+32),'R6.16 ratchet cave 2 must be stock zero and unwritten'
 put(RT2_CAVE[0],RT2_CODE,'R6.16 ratchet mono roll / live arming (M7) in checked zero cave 080DA640..080DABF0')
 aa.update(RT_SYMS)
 assert base[0x080d2500-BASE:0x080d3000-BASE]==bytes(0xb00),'P28 arp cave must be stock zero'
 put(0x080d2500,ARP_CODE,'P28 arpeggiator (M7) in checked zero cave 080D2500..080D3000')
 assert base[0x080d4400-BASE:0x080d4400-BASE+len(MEL_CODE)]==bytes(len(MEL_CODE))
 put(0x080d4400,MEL_CODE,'P14 melodic locks in checked free application cave')
 put(0x080dba00,bytes(mw),'P14 preserving adapters in checked free application cave')
 aa.update(MEL_SYMS)
 assert len(aw)<=AUDIO-0x080dc000 # CH6: adapters use <0x200; M7 code starts at 080DC400
 payload=bytes(aw)+bytes(AUDIO-0x080dc000-len(aw))+ac
 assert base[0x080dc000-BASE:0x080dc000-BASE+len(payload)]==bytes(len(payload))
 put(0x080dc000,payload,'TF2 M7 code and exact-version adapters in zero application cave')
 uw=bytearray()
 def ub(s):
  while len(uw)%4:uw.append(0)
  a=UI_STUB+len(uw);uw.extend(asm(s,a));return a
 # exp6 (owner: finer Track FX steps): the native value text formatter (type switch "subs r3,r0,#1; cmp r3,#0x13;
 # bhi; tbh", found by content in either version) prints integer descriptors (types 1/2/18) with snprintf
 # (buf=sp+8, 32, "%ld", value). Its "movs r1,#0x20; add r0,sp,#8" becomes a call of fx_value_fmt (perf_ui.c),
 # which does the same and, for a Track FX gain/Q key, writes the decimal text into the buffer and passes size 0.
 sw=bytes.fromhex('431e132b');at=[i for i in range(0,len(base)-12,2) if base[i:i+4]==sw and base[i+6:i+8]==bytes.fromhex('dfe8') and base[i+8]==0x13 and base[i+9]==0xf0]
 assert len(at)==1,'value formatter';sw=BASE+at[0]
 tbl=sw+10;case2=tbl+2*struct.unpack_from('<H',base,tbl+2-BASE)[0]
 assert base[case2-BASE:case2-BASE+2]==asm('mov r3,r7',case2) and base[case2+1-BASE]==0x46 and base[case2+3-BASE]==0x4a
 assert base[case2+4-BASE:case2+8-BASE]==asm('movs r1,#0x20; add r0,sp,#8',case2+4),'formatter call setup'
 put(case2+4,asm('bl '+hex(uu['fx_value_fmt']),case2+4),'exp6 Track FX gain/Q value text with decimals (native integer formatter)')
 # P168 exp3 (owner: Analog and drum synth pads silent after save/load): the capture sat on the common
 # exit 0812E296, where r5 is no longer the source once the node has modulation routes (the native
 # route loop from 0812E34E reuses r5 as zero), so a pad with a Mod Matrix route was never captured.
 # It now runs right after the native clear of the target (0812E27E), where r5/r6 are source/target.
 assert base[0x0812e282-BASE:0x0812e286-BASE]==asm('ldr r4,[r5,#12]; lsls r4,r4,#3',0x0812e282)
 a=ub(integer_prefix+'mov r0,r5; mov r1,r6; movs r2,#1; bl '+hex(uu['drum_copy_capture'])+'; '+integer_restore+'ldr r4,[r5,#12]; lsls r4,r4,#3; b.w 0x0812e286')
 put(0x0812e282,asm('b.w '+hex(a),0x0812e282),'Preserve frozen custom drum and Analog settings across native Save/Undo/Load node copies')
 assert base[0x0812d978-BASE:0x0812d97c-BASE]==asm('push {r3,r4,r5,r6,r7,lr}; mov r6,r0',0x0812d978)
 a=ub(integer_prefix+'ldr r0,[sp,#8]; bl '+hex(uu['drum_copy_forget'])+'; '+integer_restore+'push {r3,r4,r5,r6,r7,lr}; mov r6,r0; b.w 0x0812d97c')
 put(0x0812d978,asm('b.w '+hex(a),0x0812d978),'Release frozen custom drum settings with their native copied cell')
 def site(a,s,reason,n=4):put(a,asm(s,a)+asm('nop',a+4)*(n==6),reason)
 assert base[0x081338dc-BASE:0x081338e0-BASE]==asm('push {r4,r5,r6,lr}; sub sp,#8',0x081338dc)
 a=ub(integer_prefix+'ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(uu['live_cycle_snapshot'])+'; '+integer_restore+'push {r4,r5,r6,lr}; sub sp,#8; b.w 0x081338e0')
 site(0x081338dc,'b.w '+hex(a),'Capture per-sound cycle metadata with the native one-level note snapshot')
 assert base[0x0813b290-BASE:0x0813b294-BASE]==asm('ldr r3,[sp,#0x114]; movs r2,#0x73',0x0813b290)
 a=ub(integer_prefix+'ldr r0,[sp,#76]; ldr r1,[sp,#340]; ldr r2,[sp,#80]; bl '+hex(uu['live_cycle_restore'])+'; '+integer_restore+'ldr r3,[sp,#0x114]; movs r2,#0x73; b.w 0x0813b294')
 site(0x0813b290,'b.w '+hex(a),'Restore per-sound cycle metadata only after successful native note Undo')
 a=ub(integer_prefix+'sub sp,#8; add.w r0,sp,#616; str r0,[sp]; mov r0,r4; mov r1,r5; mov r2,r6; mov r3,r7; bl '+hex(uu['fx_dispatch'])+'; add sp,#8; cmp r0,#0; beq old; '+integer_restore+'b.w 0x0813f2fc; old: '+integer_restore+'b.w 0x081b3f40')
 site(0x0813f98c,'b.w '+hex(a),'TF2 Double-tap TRACKS shortcut before unchanged K16 consumer')
 assert base[0x081257f0-BASE:0x081257f8-BASE]==asm('push.w {r4-r11,lr}; sub sp,#44; mov r4,r0',0x081257f0)
 site(0x081257f0,'b.w '+hex(uu['play_mute_flush']),'W22 transient PLAY mute colours around native LED flush')
 a=ub(integer_prefix+'ldr r0,[sp,#8]; bl '+hex(uu['eu_view_capture'])+'; '+integer_restore+'b.w 0x081b7008')
 site(0x0815c27c,'b.w '+hex(a),'EU10 capture valid native one-shot sequence context before unchanged K16 header')
 a=ub(integer_prefix+'ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(uu['fx_nav'])+'; str r0,[sp,#12]; '+integer_restore+'push.w {r4-r8,lr}; b.w 0x081420f0')
 site(0x081420ec,'b.w '+hex(a),'Leave custom mode on ordinary navigation')
 a=ub(integer_prefix+'sub sp,#8; ldr r12,[sp,#68]; str r12,[sp]; ldr r0,[sp,#16]; ldr r1,[sp,#20]; ldr r2,[sp,#24]; ldr r3,[sp,#28]; bl '+hex(uu['fx_header'])+'; add sp,#8; cmp r0,#0; beq old; '+integer_restore+'movs r0,#1; bx lr; old: '+integer_restore+'push {r4,r5,r6,lr}; sub sp,#8; b.w 0x08134b5c')
 site(0x08134b58,'b.w '+hex(a),'Use native parameter-row menu for Track FX only')
 assert base[0x0814604e-BASE:0x08146052-BASE]==asm('bl 0x08170b7c',0x0814604e)
 put(0x0814604e,asm('bl '+hex(uu['perf_rows_layout']),0x0814604e),'Bound four Perform rows above native footer; other row layouts unchanged')
 a=ub(integer_prefix+'ldr r0,[sp,#8]; ldr r1,[sp,#12]; ldr r2,[sp,#16]; ldr r3,[sp,#20]; bl '+hex(uu['fx_get'])+'; cmp r0,#0; beq old; '+integer_restore+'movs r0,#1; bx lr; old: '+integer_restore+'push {r4,r5,r6,r7,lr}; sub sp,#12; b.w 0x08133618')
 site(0x08133614,'b.w '+hex(a),'Read private Track FX values without changing native properties')
 a=ub(integer_prefix+'ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(uu['fx_event'])+'; cmp r0,#0; beq old; '+integer_restore+'movs r0,#0; bx lr; old: '+integer_restore+'push {r4,r5,lr}; sub sp,#0x2c; b.w 0x08145d94')
 site(0x08145d90,'b.w '+hex(a),'Handle native encoder/touch events only on custom FX rows')
 for address,name,oldtarget,arg0,arg1 in [(0x0812f5ea,'fx_save',0x081bb200,'mov r0,r6','ldr r1,[sp,#8]'),(0x0812faac,'fx_load',0x081bb300,'ldr r0,[sp,#8]','ldr r1,[sp,#12]'),(0x081512a4,'fx_finish',0x081ba000,'ldr r0,[sp,#8]','ldr r1,[sp,#12]')]:
  a=ub(integer_prefix+arg0+'; '+arg1+'; bl '+hex(uu[name])+'; '+integer_restore+'b.w '+hex(oldtarget));site(address,'b.w '+hex(a),'Versioned Track FX project settings; chain original K16 hook')
 assert base[0x0812a6bc-BASE:0x0812a6c0-BASE]==asm('ldrb r3,[r4,#0x14]; subs r3,#5',0x0812a6bc)
 a=ub(integer_prefix+'mov r0,r4; bl '+hex(uu['macro_save_request'])+'; cmp r0,#0; beq save_native; '+integer_restore+'b.w 0x0812a666; save_native: '+integer_restore+'ldrb r3,[r4,#0x14]; subs r3,#5; b.w 0x0812a6c0')
 site(0x0812a6bc,'b.w '+hex(a),'Cancel dequeued native Save/Save As before filesystem work if rejected macro data could not be preserved')
 a=ub(integer_prefix+'ldr r0,=0x24041440; movs r1,#0; movw r2,#160; zero: str r1,[r0],#4; subs r2,#1; bne zero; ldr r0,=0x24041a00; movw r2,#384; state: str r1,[r0],#4; subs r2,#1; bne state; dsb; bl '+hex(uu['bb_boot'])+'; '+integer_restore+'b.w 0x081b5200')
 site(0x081004b6,'b.w '+hex(a),'Initialize new UI-owned FX memory, then original K16 startup')
 # R6.18 black box: card lines only right after stock's own card work on the UI task
 # (project-file writer 08130958 in the project save; whole-file document reader
 # 08130A18 in the two loaders). bb_card opens the file only when something is new.
 for at,orig in [(0x0813044c,0x08130958),(0x08130522,0x08130a18),(0x08130774,0x08130a18)]:
  assert base[at-BASE:at-BASE+4]==asm('bl '+hex(orig),at),('black box site',hex(at))
  a=ub('push {r4,lr}; bl '+hex(orig)+'; mov r4,r0; bl '+hex(uu['bb_card'])+'; mov r0,r4; pop {r4,pc}')
  site(at,'bl '+hex(a),'R6.18 black box: crash/boot lines after stock card work (chain '+hex(orig)+')')
 # P168 exp7 (crash cycle): our card work runs on the native file thread (pcmStreamer loop 08112B54), each time it
 # goes idle: card_poll before its 10-tick queue wait (card_idle_wait chains xQueueReceive 0812236E with the same arguments).
 assert base[0x08112bf0-BASE:0x08112bf0-BASE+4]==asm('bl 0x0812236e',0x08112bf0),'file thread idle wait'
 site(0x08112bf0,'bl '+hex(uu['card_idle_wait']),'Card work of the drum synth files on the native file thread, before its idle queue wait')
 # P168 exp3 black box: which thread the native watchdog recorder timed out on (ages into BKP[22])
 assert base[0x08107b56-BASE:0x08107b5a-BASE]==asm('mov.w lr,#5',0x08107b56)
 site(0x08107b56,'b.w '+hex(uu['bb_watchdog']),'Black box: watchdog thread ages into the unused word of the native cause 5 record')
 # Recompile exact baseline API maps, guarded by the complete K16 input hash.
 sys.path.insert(0,str(R.parents[1]/'k16_work/bento_controls'))
 import step_locks,kick_ui_build
 _,oldlocks=step_locks.compile_one('step_lock_ui','cortex_m4',False)
 # compile kick API without rebuilding or mutating the baseline binary
 subprocess.run([sys.executable,'-m','ziglang','cc','-target','thumb-freestanding-eabi','-mcpu=cortex_m4','-mfloat-abi=soft','-Oz','-g','-ffreestanding','-fno-builtin','-fno-stack-protector','-ffunction-sections','-nostdlib','-Wl,--entry=kick_ui_before','-Wl,--script='+str(R.parents[1]/'k16_work/bento_controls/kick_ui.ld'),str(R.parents[1]/'k16_work/bento_controls/kick_ui.c'),'-o',str(R/'baseline_kick_ui.elf')],check=True)
 _,oldkick=elf(R/'baseline_kick_ui.elf')
 for name in ['locks_header_before','locks_header_after','locks_encoder','locks_proj','locks_save','locks_load','locks_clear','locks_pad_clear','seq_lights_clean','locks_grid','locks_pack','locks_slot']:
  address=oldlocks[name];site(address,'b.w '+hex(uu[name]),'EU10 relocated step lock UI: '+name)
 for name in ['kick_ui_supported','kick_ui_before','kick_ui_after','kick_ui_event','kick_ui_save','kick_ui_load','kick_ui_increment','drum_ui_step']:
  address=oldkick[name];site(address,'b.w '+hex(uu[name]),'EU10 synth display cleanup: '+name)
 a=ub(integer_prefix+'ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(uu['seq_eu_arrows'])+'; cmp r0,#0; beq old; '+integer_restore+'b.w 0x0815d520; old: '+integer_restore+'ldr r3,[r1,#8]; cmp r3,#9; b.w 0x0815d582')
 site(0x0815d57e,'b.w '+hex(a),'EU10 native SEQ arrows swap encoder banks and reuse sequence navigation')
 a=ub(integer_prefix+'ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(uu['seq_eu_native_head'])+'; cmp r0,#0; beq old; '+integer_restore+'bx lr; old: '+integer_restore+'add.w r3,r0,#0x11000; b.w 0x0815bde6')
 site(0x0815bde2,'b.w '+hex(a),'EU10 generated playhead overrides native clip position only in Euclid bank')
 # Select mode uses native Undo menu's next cell, not a coordinate overlay.
 a=ub(integer_prefix+'ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(uu['seq_select_event'])+'; cmp r0,#0; beq old; '+integer_restore+'movs r0,#0; bx lr; old: '+integer_restore+'push {lr}; sub sp,#0x6c; b.w 0x0815d604')
 site(0x0815d600,'b.w '+hex(a),'EU10 native Select action dispatcher')
 import holdstep
 _,hs=holdstep.build()
 for address,name,check in [(0x0815b9c0,'step_match','seq_selection_match'),(0x0815bab0,'step_selected','seq_selection_active')]:
  # No selected mask: fall through to exact K16 held/single inspection.
  c=uu['seq_selection_active']
  body=integer_prefix+'ldr r0,[sp,#8]; bl '+hex(c)+'; cmp r0,#0; beq old; '
  if name=='step_match':body+='ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(uu[check])+'; '
  body+='str r0,[sp,#8]; '+integer_restore+'bx lr; old: '+integer_restore+'b.w '+hex(hs[name])
  if name=='step_match': # W14 HW3: stale inspected/selected steps without a note do not match
   assert hs[name]==0x081b6840
   body=integer_prefix+'ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(uu['seq_step_match'])+'; str r0,[sp,#8]; '+integer_restore+'bx lr'
  a=ub(body);site(address,'b.w '+hex(a),'EU10 persistent multi-step selection with native fallback')
 # Keystone mis-encodes Thumb-2 conditional branches (T3) to absolute targets:
 # 'bhi 0x0815d234' became bhi.w 0x0811AECE (found by tools/port/ks_branch_audit.py,
 # 10 Nov 2026). Replays use a short conditional to a local label plus b.w.
 for address,name,replay in [
  (0x0815d1ec,'seq_select_press','cmp r1,#15; bls press_in_range; b.w 0x0815d234; press_in_range: b.w 0x0815d1f0'),
  (0x0815d23c,'seq_select_release','cmp r1,#15; bls release_in_range; b.w 0x0815d296; release_in_range: b.w 0x0815d240'),
  (0x0815d29c,'seq_select_touch','push {r3,r4,r5,lr}; mov r4,r0; b.w 0x0815d2a0'),
  (0x0815d2f4,'seq_select_touch_end','add.w r3,r0,#0x11000; b.w 0x0815d2f8'),
  (0x0815d444,'seq_select_touch_end','push {r3,lr}; add.w r3,r0,#0x11000; b.w 0x0815d44a')]:
  a=ub(integer_prefix+'ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(uu[name])+'; cmp r0,#0; beq old; '+integer_restore+'bx lr; old: '+integer_restore+replay)
  site(address,'b.w '+hex(a),'EU10 selection gesture consumes native toggle path',6 if address==0x0815d444 else 4)
 # CH1 captures only the real pitched piano roll after its native header.
 replay=ub('push.w {r4-r11,lr}; b.w 0x081599c0')
 a=ub('push {r4,lr}; mov r4,r0; bl '+hex(replay)+'; mov r0,r4; bl '+hex(uu['piano_after_header'])+'; pop {r4,pc}')
 assert base[0x081599bc-BASE:0x081599c0-BASE]==bytes.fromhex('2de9f04f')
 site(0x081599bc,'b.w '+hex(a),'CH1 capture native pitched piano-roll context')
 a=ub(integer_prefix+'ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(uu['piano_event'])+'; cmp r0,#0; beq old; '+integer_restore+'movs r0,#0; bx lr; old: '+integer_restore+'push {r4-r7,lr}; sub sp,#0x174; b.w 0x0815a59c')
 assert base[0x0815a598-BASE:0x0815a59c-BASE]==bytes.fromhex('f0b5ddb0')
 site(0x0815a598,'b.w '+hex(a),'CH1 native Chord toolbar action; ordinary piano events fall through')
 # CH5: piano hardware events (vtable slot 13): arrows walk chords in live chord mode.
 a=ub(integer_prefix+'ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(uu['piano_hw'])+'; cmp r0,#0; beq old; '+integer_restore+'bx lr; old: '+integer_restore+'push {r4-r7,lr}; sub sp,#0x44; b.w 0x0815b54c')
 assert base[0x0815b548-BASE:0x0815b54c-BASE]==bytes.fromhex('f0b591b0')
 site(0x0815b548,'b.w '+hex(a),'CH5 live chord Left/Right; other piano hardware events stay native')
 # Native persistent header output; popup records alone do not populate it.
 a=ub(integer_prefix+'ldr r0,[sp,#12]; bl '+hex(uu['device_header_prepare'])+'; '+integer_restore+'push.w {r4-r11,lr}; b.w 0x0817fafc')
 assert base[0x0817faf8-BASE:0x0817fafc-BASE]==bytes.fromhex('2de9f04f')
 site(0x0817faf8,'b.w '+hex(a),'P12 custom controls at final native header application')
 assert base[0x0815c11e-BASE:0x0815c120-BASE]==bytes.fromhex('a523')
 put(0x0815c11e,asm('movs r3,#190',0x0815c11e),'W14 centre native pad selector between name column and Euclidean tab')
 replay=ub('push.w {r4-r10,lr}; b.w 0x08134804')
 a=ub('push {r4,r5,r6,lr}; mov r4,r0; mov r5,r1; bl '+hex(replay)+'; mov r2,r0; mov r0,r4; mov r1,r5; bl '+hex(uu['seq_toolbar'])+'; pop {r4,r5,r6,pc}')
 assert base[0x08134800-BASE:0x08134804-BASE]==bytes.fromhex('2de9f047')
 site(0x08134800,'b.w '+hex(a),'Persistent header custom actions (Select/Chord) with visibility sync')
 # FA has five equal native menu columns; fifth was unused. Insert Select
 # after Undo and shift Length+/Length-/Duplicate intact into cells3..5.
 menu=bytearray(base[0x08198db0-BASE:0x08198db0-BASE+100])
 assert struct.unpack_from('<I',menu)[0]==0x1032
 entry=struct.pack('<5I',0x1051,uu['select_label'],0,0,1)
 new=menu[:80]+entry
 put(0x08198db0,new,'EU10 native Undo Select Length+ Length- Duplicate menu')
 put(0x081415f8,asm('movs r3,#5',0x081415f8),'EU10 populate fifth FA menu cell')
 assert base[0x081415f0-BASE:0x081415f0-BASE+4]==bytes.fromhex('cdf804b0')
 put(0x081415f0,asm('movs r3,#4; str r3,[sp,#4]',0x081415f0),'EU10 four menu rows put fifth Select button directly right of Undo')
 # F9 has eight actions and a blank fourth cell. Reuse that blank: native
 # popup application accepts at most nine entries, despite ten stored slots.
 old_menu=base[0x08198770-BASE:0x08198770-BASE+180]
 assert struct.unpack_from('<I',old_menu)[0]==0x1032
 assert struct.unpack_from('<I',old_menu,60)[0]==0
 put(0x08198770,old_menu[:60]+old_menu[80:100]+entry+old_menu[100:],'EU10 Select beside Undo in existing blank F9 cell; preserve eight actions')
 a=ub('push {r4,r5,r6,lr}; mov r4,r0; mov r5,r1; bl 0x0816faec; mov r0,r4; mov r1,r5; bl '+hex(uu['eu_glyph_paint'])+'; mov r0,r4; mov r1,r5; bl '+hex(uu['melodic_eu_glyph_paint'])+'; pop {r4,r5,r6,pc}')
 assert base[0x0819e858-BASE:0x0819e858-BASE+4]==struct.pack('<I',0x0816faed)
 put(0x0819e858,struct.pack('<I',a|1),'EU10 sequencer-only velocity glyph after native child drawing')
 # W14 HW3 (owner): the melodic Vel Mode shows the same glyphs; the piano view (vtable 0819E7B0) draws its children through its own slot.
 a=ub('push {r4,r5,r6,lr}; mov r4,r0; mov r5,r1; bl 0x0816faec; mov r0,r4; mov r1,r5; bl '+hex(uu['melodic_eu_glyph_paint'])+'; pop {r4,r5,r6,pc}')
 assert base[0x0819e7b4-BASE:0x0819e7b4-BASE+4]==struct.pack('<I',0x0816faed)
 put(0x0819e7b4,struct.pack('<I',a|1),'W14 HW3 melodic Euclid velocity glyph after native piano child drawing')
 # CH11 drum-synth destinations in the native Mod Matrix (one-shot types 1/2).
 assert base[0x0814ce80-BASE:0x0814ce84-BASE]==bytes.fromhex('039e0f2e')
 a=ub('push {r0-r3,r12,lr}; mov r0,r4; add r1,sp,#24; bl '+hex(uu['mod_rows'])+'; pop {r0-r3,r12,lr}; ldr r6,[sp,#0xc]; cmp r6,#0xf; bx lr')
 site(0x0814ce80,'bl '+hex(a),'CH11 synth pad rows in the native Mod Matrix')
 for site_a,old,fn,why in [(0x0812f6a2,0x081666f8,'mod_token','save synth destination names'),(0x0812fe52,0x08166720,'mod_key','load synth destination names'),(0x08140924,0x08133388,'mod_edit','editing a synth route adopts the pad engine')]:
  assert base[site_a-BASE:site_a-BASE+4]==asm('bl '+hex(old),site_a),hex(site_a)
  site(site_a,'bl '+hex(uu[fn]),'CH11 Mod Matrix: '+why)
 # A1: "Analog" in the ninth (blank) cell of the native instrument menu
 # (Multisample..External at 081981F8, ten 20-byte cells); its action 1052 is
 # handled before the native menu handler (view vtable 0819E52C, 0814ECD4).
 cell=0x081981f8+8*20
 assert base[cell-BASE:cell-BASE+20]==struct.pack('<5I',0,0x0818a3d8,0,0,1)
 put(cell,struct.pack('<5I',0x1052,uu['analog_label'],0,0,1),'A1 Analog entry in the instrument menu')
 assert base[0x08141370-BASE:0x08141372-BASE]==asm('movs r3,#8',0x08141370)
 put(0x08141370,asm('movs r3,#9',0x08141370),'A1 instrument menu F6 shows nine cells (native maximum)')
 assert struct.unpack_from('<I',base,0x0819e52c-BASE)[0]==0x0814ecd5
 put(0x0819e52c,struct.pack('<I',uu['analog_menu_event']|1),'A1 instrument menu: Analog action, Wavetable clears it')
 if os.environ.get('BENTO_SYNCUSSION')=='1':
  # Melodic Syncussion: free eighth cell of the Tracks burger menu F0 (cells
  # at 08198068); the Tracks view event handler (vtable 0819EAC8 slot 12).
  cell=0x08198068+7*20
  assert base[cell-BASE:cell-BASE+20]==struct.pack('<5I',0,0x0818a3d8,0,0,1)
  # R6.3 (owner 7 Nov): Syncussion retired; no new melodic Syncussion tracks from the Tracks menu.
  assert struct.unpack_from('<I',base,0x0819eaf8-BASE)[0]==0x0816085d # R6.4: Tracks view handler stays native
 # A1 Sync on WT2's empty fourth control (Wavetable osc page key table).
 # A1b: Glide/Sync only on Analog pages, Shape label, "Analog" pane text.
 for site_a,flag in [(0x0815f5ae,0),(0x0815f68e,1)]:
  assert base[site_a-BASE:site_a-BASE+4]==asm('bl 0x08187252',site_a),hex(site_a)
  a=ub('movs r3,#'+str(flag)+'; b.w '+hex(uu['analog_page_keys']))
  put(site_a,asm('bl '+hex(a),site_a),'A1 synth page keys: '+('Wavetable/Analog' if flag else 'Granular stays native'))
 for site_a in [0x0815d968,0x0815db22,0x0815dc0e,0x0815e1ae,0x0815e1b8,0x0815e1e2]:
  assert base[site_a-BASE:site_a-BASE+4]==asm('bl 0x0817e85e',site_a),hex(site_a)
  site(site_a,'bl '+hex(uu['analog_pane_text']),'W22 waveform text resolves current instrument without stale shared buffers')
 assert base[0x081403ec-BASE:0x081403f0-BASE]==asm('push {r4,r5,r6,lr}; sub sp,#0x68',0x081403ec)
 a=ub(integer_prefix+'ldr r0,[sp,#8]; ldr r1,[sp,#12]; bl '+hex(uu['analog_model_event'])+'; cmp r0,#0; beq old; '+integer_restore+'movs r0,#0; bx lr; old: '+integer_restore+'push {r4,r5,r6,lr}; sub sp,#0x68; b.w 0x081403f0')
 site(0x081403ec,'b.w '+hex(a),'A1 model events: Analog Sync stays private')
 for address,original,name in [(0x08104296,0x081020ac,'browser_list_hook'),
                               (0x0816ca0e,0x08132db4,'browser_request')]:
  assert base[address-BASE:address-BASE+4]==asm('bl '+hex(original),address)
  put(address,asm('bl '+hex(uu[name]),address),'Carrier listing filter: '+name)
 # P20: header root events (vtable 081B3680 slot 13) pass through header_root_event.
 a=0x081b3680+13*4;assert struct.unpack_from('<I',base,a-BASE)[0]==0x0817ffb9
 put(a,struct.pack('<I',uu['header_root_event']|1),'P20 keep native tab lights off while Chord/Euclid is shown')
 # CH6 Euclidean lanes in the piano roll: the piano grid class (vtable 081B2BCC)
 # paints and ticks through lane_paint/lane_tick, which call the originals.
 # P17 (owner: the touch selection rectangle always opens at the lower middle):
 # slot 4 touch-down records the first finger as the box anchor (+A48), which the
 # native drag (mode 5, 081762B0) uses but only box mode used to set.
 for slot,old_fn,fn in [(0,0x081773a5,'lane_tick'),(1,0x08176d75,'lane_paint'),(4,0x08174999,'grid_touch_down'),(5,0x08175f39,'grid_touch_move'),(6,0x08176a29,'grid_touch_up')]:
  a=0x081b2bcc+slot*4;assert struct.unpack_from('<I',base,a-BASE)[0]==old_fn
  put(a,struct.pack('<I',uu[fn]|1),'CH6 piano-grid lanes: '+fn)
 # P27 macros: the native encoder strip (vtable 081B2838) takes touches. Its
 # touch slots [4..6] are empty stubs and [7] ("takes touches") returns 0 in
 # stock; swipes and taps on it go to macro_ui.c.
 for slot,old_fn,fn in [(0,0x081703cd,'macro_bar_tick'),(4,0x08143ac1,'macro_bar_down'),(5,0x08143ac3,'macro_bar_move'),(6,0x08143ac5,'macro_bar_up'),(7,0x08143ac7,'macro_bar_takes')]:
  a=0x081b2838+slot*4;assert struct.unpack_from('<I',base,a-BASE)[0]==old_fn
  put(a,struct.pack('<I',uu[fn]|1),'P27 macro strip touches: '+fn)
 # P28: the app's hit test (app vtable 081B2300 slot 10) routes fingers on a
 # strip to that strip before the page's own widgets (instrument page).
 assert struct.unpack_from('<I',base,0x081b2328-BASE)[0]==0x0816e0fd
 put(0x081b2328,struct.pack('<I',uu['macro_app_hit']|1),'P29 macro strip catcher where another widget wins the strip area')
 # G12: the hardware finger dispatcher calls the stock function directly,
 # bypassing the app vtable above.
 assert base[0x08163470-BASE:0x08163474-BASE]==asm('bl 0x0816e0fc',0x08163470)
 put(0x08163470,asm('bl '+hex(uu['macro_app_hit']),0x08163470),'G12 route hardware fingers through macro hit testing')
 # Launch: native paint/layout adapters plus scoped Select/group-action events.
 # Unselected/native gestures and all audio quantization stay native.
 for vt,hooks in [
  (0x0819dce0,[(0,0x0814a7a5,'pg_launch_tick'),(12,0x0814a0d1,'pg_launch_event')]),
  (0x081b298c,[(12,0x08172a09,'pg_launch_column_event')]),
  (0x081b2944,[(1,0x0816faed,'pg_launch_cell_paint'),(2,0x0816f9e9,'pg_launch_cell_walk')]),
  (0x081b35c0,[(1,0x0817e781,'pg_launch_header_paint')])]:
  for slot,old_fn,fn in hooks:
   address=vt+slot*4;assert struct.unpack_from('<I',base,address-BASE)[0]==old_fn,hex(address)
   put(address,struct.pack('<I',uu[fn]|1),'Launch native layout, markers and group selection: '+fn)
 # G1 Playground design: one-shot Step cells (class 0819E814) draw themselves;
 # data, touches and hit testing stay native.
 for slot,old_fn,fn in [(1,0x0816faed,'pg_cell_paint'),(2,0x0816f9e9,'pg_cell_walk')]:
  a=0x0819e814+slot*4;assert struct.unpack_from('<I',base,a-BASE)[0]==old_fn
  put(a,struct.pack('<I',uu[fn]|1),'G1 Playground step cell: '+fn)
 # G2 Playground design: piano grid bar lines faint (white alpha 6) instead of F6.
 assert base[0x08176ee2-BASE:0x08176ee4-BASE]==bytes.fromhex('f622')
 put(0x08176ee2,bytes.fromhex('6222'),'G2 Playground piano grid: faint bar lines')
 # Run 15 item C (owner, 13 Nov): shared native SectionGroup + footer tab in the Clean look (port/clean_blocks.py,
 # both versions' addresses; constant halfwords only, each checked against stock).
 sys.path.insert(0,str(R/'port'));import clean_blocks as _clean;sys.path.pop(0)
 _clean.m4(_ids.BENTO_FW,base,BASE,put,uu)
 # W5: approved Tracks-only polish. Native tick/model/output bindings remain;
 # the shared encoder bar falls through on every other page, including Mixer.
 for vt,hooks in [
  (0x081b38d0,[(1,0x0816faed,'pg_column_paint'),(2,0x0816f9e9,'pg_column_walk'),
               (4,0x08143ac1,'pg_column_down'),(5,0x08143ac3,'pg_column_move'),
               (6,0x08143ac5,'pg_column_up'),(10,0x0816fa11,'pg_column_hit')]),
  (0x081b2838,[(1,0x0816faed,'pg_bar_paint'),(2,0x0816f9e9,'pg_bar_walk')]),
  (0x0819eac8,[(0,0x08160a21,'pg_tracks_tick'),(13,0x08160fb5,'pg_tracks_event')])]:
  for slot,old_fn,fn in hooks:
   address=vt+slot*4;assert struct.unpack_from('<I',base,address-BASE)[0]==old_fn,hex(address)
   put(address,struct.pack('<I',uu[fn]|1),'W5 Tracks: '+fn)
 for slot,old_fn,fn in [(0,0x081b5001,'pg_mixer_tick'),
                       (1,0x0816faed,'pg_mixer_paint'),(2,0x0816f9e9,'pg_mixer_walk'),
                       (4,0x0814b01b,'pg_mixer_down'),(5,0x0814afa3,'pg_mixer_move'),
                       (6,0x0814a809,'pg_mixer_up'),(10,0x0814a7bd,'pg_mixer_hit'),
                       (12,0x0814baeb,'pg_mixer_receive'),(13,0x0814b98d,'pg_mixer_event')]:
  address=0x0819dd20+slot*4;assert struct.unpack_from('<I',base,address-BASE)[0]==old_fn
  put(address,struct.pack('<I',uu[fn]|1),'W7 Mixer: '+fn)
 # Minimalist one-shot tiles retain native playback/level/status children.
 # BENTO_STOCK_INST still keeps the retired hold-INST shortcut disabled.
 for slot,old_fn,fn in [(1,0x0816faed,'inst_bank_paint'),(2,0x0816f9e9,'inst_bank_walk')]:
  address=0x081b2e88+slot*4
  assert struct.unpack_from('<I',base,address-BASE)[0]==old_fn
  put(address,struct.pack('<I',uu[fn]|1),'Minimalist INST bank: '+fn)
 # Static label colours only: native tile paint/walk and playback stay exact.
 for address in [0x08179564,0x08179770,0x081797be,0x081797e6]:
  assert base[address-BASE:address-BASE+4]==asm('bl 0x0817948a',address)
  put(address,asm('bl '+hex(uu['inst_bank_colours']),address),'INST native static-label track colours')
 if XY: # P168 exp8: XY per-track send (port/xy_168.py, 1.6.8 addresses)
  XY.m7(base,BASE,asm,put,image);XY.m4(base,BASE,asm,put,uu);FXV.m4(base,BASE,asm,put,uu)
 assert len(uw)<=0x800
 global UI_ADAPTER_TAIL;UI_ADAPTER_TAIL=[UI_STUB+((len(uw)+3)&~3),UI]
 append=BASE+len(base);assert append==UI_STUB
 bank1=[(a,c) for a,c in UI_PAD if a in dict(UI_BANK1) and c]
 if bank1 and os.environ.get('BENTO_M4_MPU_WIDE')!='1':
  raise SystemExit('Bank-1 M4 code ('+', '.join('%08X+%d'%(a,len(c)) for a,c in bank1)+') needs BENTO_M4_MPU_WIDE=1: the stock M4 MPU cannot execute flash bank 1')
 for a,code in UI_PAD:
  code=code+b'\0'*(-len(code)%4)
  if a in dict(UI_BANK1):
   end=dict(UI_BANK1)[a];assert a+len(code)<=end,('bank-1 M4 section overflow',hex(a),len(code))
   run=next(lo for lo,hi in BANK1_RUNS if lo<=a and end==hi);assert a-run>=0x10
   # Must be stock zero (K16 base) and still untouched by every earlier write.
   assert base[run-BASE:end-BASE]==bytes(end-run),'Bank-1 M4 cave must be stock zero %08X..%08X'%(run,end)
   assert bytes(image[run-BASE:end-BASE])==bytes(end-run),'Bank-1 M4 cave already written %08X..%08X'%(run,end)
   if code:put(a,code,'Bank-1 M4: UI code in checked zero cave %08X..%08X (MPU region 1 widened)'%(a,end))
   continue
  if a in dict(UI_RETIRED):
   end=dict(UI_RETIRED)[a]
   assert len(code)<=end-a
   # Every externally callable function in these old C bodies is forwarded
   # above. The first instructions, fixed native trampolines, and other
   # inherited sections remain untouched; K16_SHA guards exact old contents.
   assert all(not(a<=x<a+len(code)) for x in oldlocks.values() if x in [
    oldlocks[n] for n in ['locks_header_before','locks_header_after','locks_encoder','locks_proj','locks_save','locks_load','locks_clear','locks_pad_clear','seq_lights_clean','locks_grid','locks_pack','locks_slot']])
   assert all(not(a<=oldkick[n]<a+len(code)) for n in ['kick_ui_supported','kick_ui_before','kick_ui_after','kick_ui_event','kick_ui_save','kick_ui_load','kick_ui_increment','drum_ui_step'])
   put(a,code,'Kit/Seq code in retired K16 UI body %08X..%08X; forwarding entries preserved'%(a,end))
  else:
   end=dict(UI_PADS)[a];assert base[a-0x10-BASE:end-BASE]==bytes(end-a+0x10),'K16 padding must be zero'
   put(a,code,'W14 HW3 UI code in checked K16 zero padding %08X..%08X'%(a,end))
 # Run 13: new pads (guards included) are zero and unreferenced in K16; the five K16 condition stubs are entered
 # from nowhere in this image (each native site now branches elsewhere) and from nothing else in K16.
 for lo,hi in RUN13_PADS:assert base[lo-0x10-BASE:hi+0x10-BASE]==bytes(hi-lo+0x20),'run-13 pad guard %08X'%lo
 lo,hi=RUN13_RETIRED_STUBS;_k16_unreferenced(base,[(lo-0x10,lo)]+[(a-0x10,b+0x10) for a,b in RUN13_PADS])
 stubs=sorted(x for x in _branch_targets(base) if lo<=(x&~1)<hi+0x10);sites=_branch_targets(bytes(image))
 assert len(stubs)==5 and all(base[s-BASE:s-BASE+4]!=image[s-BASE:s-BASE+4] for s in RUN13_STUB_SITES),('K16 condition stubs',[hex(x) for x in stubs])
 assert base[hi-BASE:hi+0x10-BASE]==bytes(16) and not any(lo<=(x&~1)<hi+0x10 for x in sites if not lo<=x<hi),'retired condition stubs still referenced'
 assert base[0x08171e44-BASE:0x08171e48-BASE]==asm('b.w 0x081bc660',0x08171e44)
 assert bytes(image[0x081bc660-BASE:0x081bc6a0-BASE])==base[0x081bc660-BASE:0x081bc6a0-BASE]
 assert len(uw)+16<=UI-append,'UI stub adapters (%d B) no longer fit below the UI code at %08X'%(len(uw),UI)
 body=bytes(uw)+bytes(UI-append-len(uw))+uc
 body+=b'BENTO_MOD:Chord:CH1:1.0\0';body+=b'\xff'*(-len(body)%4)
 assert append+len(body)<=0x081e0000,'Complete application including trailer must stay below 081E0000'
 put(append,body,'TF2 native settings UI implementation, application flash only')
 for a in [0x08040588,0x080a3bdc,0x080a3e94]:
  assert struct.unpack_from('<I',base,a-BASE)[0]==0x24042000;put(a,struct.pack('<I',0x24040000),'Reserve 8KB for Track FX inside native MPU permissions; stack unchanged')
 # Preserve the old P17 preimage check; BENTO_STOCK_INST now removes the shortcut
 # in the rebuilt controls instead of patching an obsolete body offset.
 assert base[0x081b43b8-BASE:0x081b43bc-BASE]==bytes.fromhex('00262728')
 put(0x0818bad4,b'1.6W22\0','Visible W22 Wavetable Position Motion and PLAY mute feedback')
 for a,n in [(BASE,0x400),(0x080e0000,0x20000),(0x08100000,0x400)]:assert image[a-BASE:a-BASE+n]==base[a-BASE:a-BASE+n]
 restored=bytearray(image)
 for w in reversed(writes):
  off=w['address']-BASE;restored[off:off+w['size']]=bytes.fromhex(w['original_hex'])
 restored=restored[:len(base)];assert bytes(restored)==base
 return bytes(image),writes,aa,uu
if __name__=='__main__':
 b=Path(sys.argv[1]).read_bytes();image,writes,aa,uu=build(b);out=Path(sys.argv[2]);out.mkdir(exist_ok=True)
 (out/'bento1.bin').write_bytes(image);(out/'manifest.json').write_text(json.dumps(dict(label='1.6P22',base_sha256=K16_SHA,sha256=hashlib.sha256(image).hexdigest(),writes=writes,audio_symbols=aa,ui_symbols=uu,ui_adapter_tail=UI_ADAPTER_TAIL),indent=2)+'\n')
 print('EU10 built:',len(image),'bytes; exact K16 restore verified')
