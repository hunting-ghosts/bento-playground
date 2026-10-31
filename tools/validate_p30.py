"""Validate a candidate image and require complete unittest summaries."""
import argparse,os,subprocess,sys,re,json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--stock',type=Path,required=True);p.add_argument('--core',type=Path,required=True);p.add_argument('--resume',action='store_true');p.add_argument('--only',default='',help='comma-separated name parts, e.g. motion,safety (quick check, no summary)');p.add_argument('--dsp-baseline',type=Path,help='Untouched source reproduction with DSP_RESULTS.txt; records an identical numerical failure explicitly');a=p.parse_args();out=a.build.resolve()
env=dict(os.environ,MOTION_CANDIDATE=str(out),BENTO_CHORD_TEST_ORIGIN='0x081e0000',PYTHONPATH=os.pathsep.join([str(out/'workspace/chord_work'),str(out/'workspace/eu4_work/integration'),str(out/'workspace/motion_work')]),BENTO_FX_CANDIDATE=str(out),BENTO_K16_IMAGE=str(out/'baseline/bento1.bin'),BENTO_STOCK_IMAGE=str(a.stock.resolve()),BENTO_CHORD_BUILD=str(a.core.resolve()),BENTO_LOCK_IMAGE=str(a.stock.resolve()),BENTO_ZIG_PYTHON=sys.executable)
W=out/'workspace'
runs=[(name.upper()+'_RESULTS',[sys.executable,str(W/f'eu4_work/integration/test_{name}.py')]) for name in ['safety','gestures','integration','previous_controls','live','editable_eu','eu7','eu8','eu9','eu10','melodic','chord_audition','record_takeover','mod_matrix','analog_ui','perf','drum_menu','mod','p12','macro','arp']]
runs += [('CONTROLS_E3_RESULTS',[sys.executable,str(W/'eu4_work/test_controls_e3.py')]),('DSP_RESULTS',[sys.executable,str(W/'eu4_work/track_fx/build.py')]),('VISUAL_RESULTS',[sys.executable,str(R/'tools/test_visual_isolated.py'),'--suite',str(W/'eu4_work/test_eu5.py')]),('K16_REGRESSIONS',[sys.executable,str(W/'eu4_work/test_k16_regressions.py')]),('MOD_MATRIX_AUDIO_RESULTS',[sys.executable,str(W/'eu4_work/test_mod_matrix_audio.py')]),('ENGINE_RESULTS',[sys.executable,str(W/'eu4_work/test_engines.py')]),('CHORD_RESULTS',[sys.executable,'-m','unittest','discover','-s',str(W/'chord_work'),'-p','test_*.py','-v'])]
runs += [('MACRO_TOUCH_DISPATCH_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_macro_touch_dispatch.py')])]
manifest=json.loads((out/'FULL_MANIFEST.json').read_text())
if manifest['label'] in ('1.6W21','1.6W22','Preview 0.1','Alpha 1.0'):
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
if (W/'eu4_work/integration/test_encoder_speed.py').exists():
 runs += [('ENCODER_SPEED_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_encoder_speed.py')])]
if 'pg_launch_tick' in json.loads((out/'manifest.json').read_text()).get('ui_symbols',{}):
 runs += [('LAUNCH_RESULTS',[sys.executable,str(W/'eu4_work/integration/test_launch.py')])]
M=W/'motion_work'
if (out/'MOTION_MANIFEST.json').exists():runs += [('MOTION_PRODUCER_RESULTS',[sys.executable,str(M/'test_native_producer.py'),'--image',str(out/'fx/bento1.bin')]),('MOTION_AUDIO_RESULTS',[sys.executable,str(M/'test_native_audio.py'),'--image',str(out/'bento1.bin'),'--elf',str(out/'motion_audio.elf')]),('MOTION_END_TO_END_RESULTS',[sys.executable,str(M/'test_motion_end_to_end.py'),'--image',str(out/'fx/bento1.bin'),'--elf',str(out/'motion_audio.elf')]),('MOTION_SETTINGS_RESULTS',[sys.executable,str(M/'test_motion_settings_ui.py')])]
runs += [('SUBTRACTIVE_RESULTS',[sys.executable,str(W/'eu4_work/test_subtractive.py')]),('ANALOG_RESULTS',[sys.executable,str(W/'eu4_work/test_analog.py')])]
counts={};known_failures={};skipped={}
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
 assert result.returncode==0 and m and re.search(r'\bOK(?: \(skipped=\d+\))?\s*$',log),name+' incomplete or failed'
 record_count(name,log,int(m[-1]));print(name,counts[name],'passed;',skipped[name],'skipped',flush=True)
if a.only:print('Quick check passed:',counts);sys.exit(0)
(out/'VALIDATION_SUMMARY.json').write_text(json.dumps(dict(suites=counts,total=sum(counts.values()),skipped={k:v for k,v in skipped.items() if v},known_baseline_failures=known_failures),indent=2)+'\n');print('Total',sum(counts.values()),'software checks passed;',sum(skipped.values()),'skipped;',len(known_failures),'known baseline failures')
