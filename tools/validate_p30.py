"""Validate a candidate image and require complete unittest summaries."""
import argparse,os,subprocess,sys,re,json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--stock',type=Path,required=True);p.add_argument('--core',type=Path,required=True);p.add_argument('--resume',action='store_true');p.add_argument('--keep-going',action='store_true',help='port work: run every suite and summarise failures instead of stopping at the first (never a release gate)');p.add_argument('--only',default='',help='comma-separated name parts, e.g. motion,safety (quick check, no summary)');p.add_argument('--dsp-baseline',type=Path,help='Untouched source reproduction with DSP_RESULTS.txt; records an identical numerical failure explicitly');a=p.parse_args();out=a.build.resolve()
env=dict(os.environ,MOTION_CANDIDATE=str(out),BENTO_CHORD_TEST_ORIGIN='0x081e0000',PYTHONPATH=os.pathsep.join([str(out/'workspace/chord_work'),str(out/'workspace/eu4_work/integration'),str(out/'workspace/motion_work')]),BENTO_FX_CANDIDATE=str(out),BENTO_K16_IMAGE=str(out/'baseline/bento1.bin'),BENTO_STOCK_IMAGE=str(a.stock.resolve()),BENTO_CHORD_BUILD=str(a.core.resolve()),BENTO_LOCK_IMAGE=str(a.stock.resolve()),BENTO_ZIG_PYTHON=sys.executable)
W=out/'workspace'
runs=[(name.upper()+'_RESULTS',[sys.executable,str(W/f'eu4_work/integration/test_{name}.py')]) for name in ['safety','gestures','integration','previous_controls','live','editable_eu','eu7','eu8','eu9','eu10','melodic','chord_audition','record_takeover','mod_matrix','analog_ui','perf','drum_menu','mod','p12','macro','arp']]
if (W/'eu4_work/integration/test_lock_codec.py').exists():
 runs += [('LOCK_CODEC_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_lock_codec.py')])]
if (W/'eu4_work/test_drum_audio_host.py').exists():
 runs += [('DRUM_AUDIO_HOST_RESULTS',[sys.executable,str(W/'eu4_work/test_drum_audio_host.py')])]
if (W/'eu4_work/test_drum_audio.py').exists():
 runs += [('DRUM_AUDIO_RESULTS',[sys.executable,str(W/'eu4_work/test_drum_audio.py')])]
runs += [('CONTROLS_E3_RESULTS',[sys.executable,str(W/'eu4_work/test_controls_e3.py')]),('DSP_RESULTS',[sys.executable,str(W/'eu4_work/track_fx/build.py')]),('VISUAL_RESULTS',[sys.executable,str(R/'tools/test_visual_isolated.py'),'--suite',str(W/'eu4_work/test_eu5.py')]),('K16_REGRESSIONS',[sys.executable,str(W/'eu4_work/test_k16_regressions.py')]),('MOD_MATRIX_AUDIO_RESULTS',[sys.executable,str(W/'eu4_work/test_mod_matrix_audio.py')]),('ENGINE_RESULTS',[sys.executable,str(W/'eu4_work/test_engines.py')]),('CHORD_RESULTS',[sys.executable,'-m','unittest','discover','-s',str(W/'chord_work'),'-p','test_*.py','-v'])]
runs += [('TRANSPOSE_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_transpose.py')])] # R6.6
if (W/'eu4_work/integration/test_ratchet_play.py').exists():
 runs += [('RATCHET_PLAY_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_ratchet_play.py')])] # R6.13
for nm,rel in (('RATCHET_MONO_ROLL_RESULTS','eu4_work/test_ratchet_mono_roll.py'),('RATCHET_E2E_RESULTS','eu4_work/integration/test_ratchet_e2e.py'),('RATCHET_INERT_RESULTS','eu4_work/test_ratchet_inert.py'),('TRIGGER_CONDITIONS_RESULTS','eu4_work/integration/test_trigger_conditions.py'),('BLACKBOX_RESULTS','eu4_work/integration/test_blackbox.py')):
 if (W/rel).exists():runs += [(nm,[sys.executable,str(W/rel)])] # R6.16
if (W/'eu4_work/test_kick_retrigger_native.py').exists():
 runs += [('KICK_RETRIGGER_NATIVE_RESULTS',[sys.executable,str(W/'eu4_work/test_kick_retrigger_native.py')])] # R6.15
if (W/'eu4_work/integration/test_ratchet_ui.py').exists():
 runs += [('RATCHET_UI_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_ratchet_ui.py')])] # R6.14
runs += [('MACRO_TOUCH_DISPATCH_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_macro_touch_dispatch.py')])]
if (W/'eu4_work/integration/test_ui_rt.py').exists():
 runs += [('UI_RT_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_ui_rt.py')])] # 1.6.8 port: compact UI 64-bit division
manifest=json.loads((out/'FULL_MANIFEST.json').read_text())
env['BENTO_SYNCUSSION']='1' if manifest.get('syncussion') else '0'
if manifest.get('syncussion'):
 runs += [('SYNCUSSION_HOST_RESULTS',[sys.executable,str(W/'eu4_work/test_syncussion_host.py')]),
          ('SYNCUSSION_RESULTS',[sys.executable,str(W/'eu4_work/test_syncussion.py')]),
          ('SYNCUSSION_UI_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_syncussion_ui.py')])]
 if (W/'eu4_work/test_hihat_native.py').exists():
  runs += [('HIHAT_NATIVE_RESULTS',[sys.executable,str(W/'eu4_work/test_hihat_native.py')])]
 if (W/'eu4_work/integration/test_drum_panel.py').exists():
  runs += [('DRUM_PANEL_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_drum_panel.py')])]
 if (W/'eu4_work/integration/test_kit_seq.py').exists():
  runs += [('KIT_SEQ_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_kit_seq.py')])]
 if (W/'eu4_work/integration/test_syncussion_melodic_ui.py').exists():
  runs += [('SYNCUSSION_MELODIC_UI_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_syncussion_melodic_ui.py')])]
 for name in ('drum_motion','syncussion_persistence'):
  if (W/f'eu4_work/integration/test_{name}.py').exists():
   runs += [(name.upper()+'_RESULTS',[sys.executable,str(W/f'eu4_work/integration/test_{name}.py')])]
if manifest.get('clip_motion') or manifest['label'] in ('1.6W21','1.6W22','Preview 0.1','Alpha 1.0','Bento Playground Diagnostics 1.0','Bento Playground Diagnostics 2.0','Bento Playground Diagnostics 2.1'):
 runs += [('PLAY_MUTES_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_play_mutes.py')])]
if manifest.get('clip_motion'):
 runs += [(name.upper()+'_RESULTS',[sys.executable,str(W/f'eu4_work/integration/test_{name}.py')]) for name in ['clip_motion','native_automation']]
 # W15 inherits the complete W14 workflow regression contract.
 manifest=dict(manifest,label='1.6W14')
if manifest.get('native_motion'):
 runs += [(name.upper()+'_RESULTS',[sys.executable,str(W/f'eu4_work/integration/test_{name}.py')]) for name in ['native_motion','native_automation']]
if manifest['label'] in ('1.6W1','1.6W2','1.6W3','1.6W4','1.6W5','1.6W6','1.6W7','1.6W8','1.6W9','1.6W10','1.6W11','1.6W13','1.6W14'):
 runs += [(name.upper()+'_RESULTS',[sys.executable,str(W/f'eu4_work/integration/test_{name}.py')]) for name in ['workflow','lock_touch','macro_persistence']]
if manifest['label'] in ('1.6W5','1.6W6','1.6W7','1.6W8','1.6W9','1.6W10','1.6W11','1.6W13','1.6W14'):
 runs += [('TRACKS_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_tracks.py')])]
if manifest['label'] in ('1.6W7','1.6W8','1.6W9','1.6W10','1.6W11','1.6W13','1.6W14'):
 runs += [('MIXER_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_mixer.py')])]
if manifest['label'] in ('1.6W10','1.6W11','1.6W13','1.6W14'):
 runs += [('PERFORM_UI_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_perform_ui.py')])]
if (W/'eu4_work/integration/test_oneshot_inst.py').exists():
 runs += [('ONESHOT_INST_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_oneshot_inst.py')])]
if (W/'eu4_work/integration/test_encoder_speed.py').exists():
 runs += [('ENCODER_SPEED_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_encoder_speed.py')])]
for name in ('browser_filter','fx_meter_contract','fx_meter_audio','fx_meter_ui','multisample_reload','manual_cycle','inst_bank','send_motion','project_roundtrip','xy_send','fxviews','trackfx_v5','device168'):
 if (W/f'eu4_work/integration/test_{name}.py').exists():
  runs += [(name.upper()+'_RESULTS',[sys.executable,str(W/f'eu4_work/integration/test_{name}.py')])]
if manifest.get('syncussion') and (W/'eu4_work/test_syncussion_native.py').exists():
 runs += [('SYNCUSSION_NATIVE_RESULTS',[sys.executable,str(W/'eu4_work/test_syncussion_native.py')])]
if (W/'eu4_work/integration/test_playground_optimization.py').exists():
 runs += [('PLAYGROUND_OPTIMIZATION_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_playground_optimization.py')])]
if 'pg_launch_tick' in json.loads((out/'manifest.json').read_text()).get('ui_symbols',{}):
 runs += [('LAUNCH_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_launch.py')])]
# Unicorn can terminate during callback teardown between these tests without
# a unittest summary. Keep every assertion, but isolate their emulator lifetime.
runs=[(name,[sys.executable,str(R/'tools/test_suite_isolated.py'),'--suite',cmd[1]])
      if name in ('PLAY_MUTES_RESULTS','CLIP_MOTION_RESULTS','MOD_MATRIX_RESULTS','DRUM_MENU_RESULTS','MACRO_RESULTS') else (name,cmd)
      for name,cmd in runs]
M=W/'motion_work'
if (out/'MOTION_MANIFEST.json').exists():runs += [('MOTION_PRODUCER_RESULTS',[sys.executable,str(M/'test_native_producer.py'),'--image',str(out/'fx/bento1.bin')]),('MOTION_AUDIO_RESULTS',[sys.executable,str(M/'test_native_audio.py'),'--image',str(out/'bento1.bin'),'--elf',str(out/'motion_audio.elf')]),('MOTION_END_TO_END_RESULTS',[sys.executable,str(M/'test_motion_end_to_end.py'),'--image',str(out/'fx/bento1.bin'),'--elf',str(out/'motion_audio.elf')]),('MOTION_SETTINGS_RESULTS',[sys.executable,str(M/'test_motion_settings_ui.py')])]
runs += [('SUBTRACTIVE_RETIREMENT_RESULTS',[sys.executable,str(W/'eu4_work/test_subtractive.py')]),('ANALOG_RESULTS',[sys.executable,str(W/'eu4_work/test_analog.py')])]
counts={};known_failures={};skipped={};failed_suites={}
def record_count(name,log,total):
 match=re.search(r'OK \(skipped=(\d+)\)\s*$',log)
 skipped[name]=int(match[1]) if match else 0
 counts[name]=total-skipped[name]
def baseline_dsp(log):
 if not a.dsp_baseline:return False
 baseline=a.dsp_baseline.resolve();prior=(baseline/'DSP_RESULTS.txt').read_text()
 failure='test_m7_matches_host_audio_with_real_eq_and_compression'
 signature=r'AssertionError: ([0-9.e+-]+) not less than (0\.0002)\b'
 if re.findall(r'^FAIL: (\w+)',log,re.M)!=[failure] or re.findall(r'^FAIL: (\w+)',prior,re.M)!=[failure]:return False
 if re.findall(signature,log)!=re.findall(signature,prior) or not re.findall(signature,log):return False
 if 'Ran 38 tests' not in log or 'FAILED (failures=1)' not in log or 'FAILED (failures=1)' not in prior:return False
 for name,digest in json.loads((out/'SOURCE_INPUTS.json').read_text()).items():
  if name.startswith('eu4_work/track_fx/'):
   assert hashlib.sha256((baseline/name).read_bytes()).hexdigest()==digest,'DSP baseline source differs: '+name
 (out/'DSP_BASELINE_RESULTS.txt').write_text(prior)
 known_failures['DSP_RESULTS']={'test':failure,'assertion':re.findall(signature,log)[0],'baseline_source_identical':True}
 return True
if a.only:runs=[r for r in runs if any(k.strip().upper() in r[0] for k in a.only.split(','))];assert runs,'--only matched no suite'
for name,cmd in runs:
 previous=out/(name+'.txt')
 if a.resume and previous.exists():
  log=previous.read_text();m=re.findall(r'Ran (\d+) tests?\b',log)
  if m and re.search(r'\bOK(?: \(skipped=\d+\))?\s*$',log):
   record_count(name,log,int(m[-1]));print(name,counts[name],'passed (already checked this image)',flush=True);continue
  if name=='DSP_RESULTS' and m and baseline_dsp(log):
   counts[name]=int(m[-1])-1;print(name,counts[name],'passed; 1 identical baseline numerical failure (already checked, NOT a green suite)',flush=True);continue
 if len(cmd)>1 and cmd[1].endswith('.py'):
  cmd=[cmd[0],str(R/'tools/run_arm_suite.py'),*cmd[1:]]
 print('Checking',name,flush=True)
 with (out/(name+'.txt')).open('w') as f:result=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,cwd=R)
 log=(out/(name+'.txt')).read_text();m=re.findall(r'Ran (\d+) tests?\b',log)
 if name=='DSP_RESULTS' and result.returncode and baseline_dsp(log):
  counts[name]=int(m[-1])-1;print(name,counts[name],'passed; 1 identical baseline numerical failure (NOT a green suite)',flush=True);continue
 ok=result.returncode==0 and m and re.search(r'\bOK(?: \(skipped=\d+\))?\s*$',log)
 if not ok and a.keep_going:
  f_=len(re.findall(r'^(FAIL|ERROR):',log,re.M));failed_suites[name]=dict(ran=int(m[-1]) if m else 0,failures=f_,returncode=result.returncode)
  print(name,'FAILED: ran',failed_suites[name]['ran'],'failures/errors',f_,flush=True);continue
 assert ok,name+' incomplete or failed'
 record_count(name,log,int(m[-1]));print(name,counts[name],'passed;',skipped[name],'skipped',flush=True)
if a.keep_going:
 (out/'PORT_SUITES.json').write_text(json.dumps(dict(passed=counts,skipped=skipped,failed=failed_suites),indent=1)+'\n')
 print('keep-going: %d suites green (%d checks), %d suites failing: %s'%(len(counts),sum(counts.values()),len(failed_suites),', '.join(failed_suites)));sys.exit(1 if failed_suites else 0)
if a.only:print('Quick check passed:',counts);sys.exit(0)
(out/'VALIDATION_SUMMARY.json').write_text(json.dumps(dict(image_sha256=hashlib.sha256((out/'bento1.bin').read_bytes()).hexdigest(),source_inputs_sha256=hashlib.sha256((out/'SOURCE_INPUTS.json').read_bytes()).hexdigest(),suites=counts,total=sum(counts.values()),skipped={k:v for k,v in skipped.items() if v},known_baseline_failures=known_failures),indent=2)+'\n');print('Total',sum(counts.values()),'software checks passed;',sum(skipped.values()),'skipped;',len(known_failures),'known baseline failures')
