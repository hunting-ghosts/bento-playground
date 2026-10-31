"""Verify Python and browser patchers against the exact release image and ZIPs."""
from pathlib import Path
import argparse,copy,importlib.util,json,os,subprocess,tempfile,unittest,zipfile,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'patcher'))
from patch_bento import apply_patch,make_zip
p=argparse.ArgumentParser();p.add_argument('--patcher',type=Path,required=True);p.add_argument('--stock-dir',type=Path,required=True);p.add_argument('--image',type=Path,required=True);args=p.parse_args();directory=args.patcher.resolve();stock=(args.stock_dir/'bento1.bin').read_bytes();controller=(args.stock_dir/'bento2.bin').read_bytes();image=args.image.read_bytes();patch_files=list(directory.glob('*.patch.json'));assert len(patch_files)==1;patch=json.loads(patch_files[0].read_text())
class Tests(unittest.TestCase):
 def test_python_output_matches_release_byte_for_byte(self):self.assertEqual(apply_patch(stock,controller,patch),image)
 def test_python_rejects_modified_truncated_and_wrong_controller_inputs(self):
  for main,board in [(stock[:-1],controller),(image,controller),(b'X'+stock[1:],controller),(stock,b'X'+controller[1:])]:
   with self.assertRaises(ValueError):apply_patch(main,board,patch)
 def test_python_rejects_tampered_patch_and_bad_bounds(self):
  for mode in [0,1]:
   bad=copy.deepcopy(patch)
   if mode:bad['writes'][1][0]=0
   else:bad['output_sha256']='0'*64
   with self.assertRaises(ValueError):apply_patch(stock,controller,bad)
 def test_python_zip_has_exact_firmware_restore_and_synth_markers(self):
  import io
  with zipfile.ZipFile(io.BytesIO(make_zip(stock,controller,image,patch))) as z:
   self.assertIsNone(z.testzip());self.assertEqual(z.read('01_TEST_FIRMWARE/bento1.bin'),image);self.assertEqual(z.read('01_TEST_FIRMWARE/bento2.bin'),controller);self.assertEqual(z.read('03_STOCK_RESTORE/bento1.bin'),stock);self.assertEqual(z.read('03_STOCK_RESTORE/bento2.bin'),controller);self.assertEqual(len([n for n in z.namelist() if n.endswith('.wav')]),len(patch['carriers']))
   if patch.get('source_url'):self.assertIn(patch['source_url'],z.read('SOURCE.txt').decode())
   for line in z.read('SHA256SUMS.txt').decode().splitlines():
    digest,name=line.split('  ',1);self.assertEqual(__import__('hashlib').sha256(z.read(name)).hexdigest(),digest)
 def test_browser_javascript_and_zip_match_verified_release(self):
  script=r'''
const fs=require('fs'),vm=require('vm');const html=fs.readFileSync(process.argv[2],'utf8'),nodes={};const ctx={crypto:require('crypto').webcrypto,TextEncoder,Uint8Array,Uint32Array,DataView,Blob,atob,console,document:{getElementById:id=>nodes[id]??(nodes[id]={})}};vm.createContext(ctx);vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],ctx);
(async()=>{ctx.stock=new Uint8Array(fs.readFileSync(process.argv[3]));ctx.controller=new Uint8Array(fs.readFileSync(process.argv[4]));ctx.result=await vm.runInContext('applyPatch(stock,controller)',ctx);fs.writeFileSync(process.argv[5],ctx.result);const zip=await vm.runInContext('makeZip(stock,controller,result)',ctx);fs.writeFileSync(process.argv[6],Buffer.from(await zip.arrayBuffer()));for(const expr of ['applyPatch(stock.slice(1),controller)','applyPatch(result,controller)','applyPatch(stock,controller.slice(1))','applyPatch(stock,controller,{...PATCH,output_sha256:"0".repeat(64)})','applyPatch(stock,controller,{...PATCH,output_size:0x1a0004})','applyPatch(stock,controller,{...PATCH,writes:[[1,"AA=="],[0,"AA=="]]})','applyPatch(stock,controller,{...PATCH,writes:[[PATCH.output_size,"AA=="]]})']){let rejected=false;try{await vm.runInContext(expr,ctx)}catch(e){rejected=true}if(!rejected)throw Error('Browser accepted invalid input: '+expr);}console.log('Browser output and seven refusal cases verified');})().catch(e=>{console.error(e);process.exitCode=1});
'''
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);js=d/'check.js';js.write_text(script);out=d/'bento1.bin';zfile=d/'install.zip'
   subprocess.run(['node',str(js),str(directory/'OPEN_BENTO_PATCHER.html'),str((args.stock_dir/'bento1.bin').resolve()),str((args.stock_dir/'bento2.bin').resolve()),str(out),str(zfile)],check=True)
   self.assertEqual(out.read_bytes(),image)
   with zipfile.ZipFile(zfile) as z:
    self.assertIsNone(z.testzip());self.assertEqual(z.read('01_TEST_FIRMWARE/bento1.bin'),image);self.assertEqual(z.read('01_TEST_FIRMWARE/bento2.bin'),controller);self.assertEqual(z.read('03_STOCK_RESTORE/bento1.bin'),stock);self.assertEqual(z.read('03_STOCK_RESTORE/bento2.bin'),controller);self.assertIn('\n1. Back',z.read('00_START_HERE.txt').decode());self.assertNotIn('\\n',z.read('SHA256SUMS.txt').decode());self.assertEqual(len([n for n in z.namelist() if n.endswith('.wav')]),len(patch['carriers']))
    for line in z.read('SHA256SUMS.txt').decode().splitlines():
     digest,name=line.split('  ',1);self.assertEqual(__import__('hashlib').sha256(z.read(name)).hexdigest(),digest)
 def test_patcher_has_no_network_requests_or_original_firmware_files(self):
  html=(directory/'OPEN_BENTO_PATCHER.html').read_text()
  self.assertNotIn('fetch(',html);self.assertNotIn('XMLHttpRequest',html);self.assertNotIn('<script src=',html);self.assertNotIn('__LABEL__',html);self.assertNotIn('__RELEASE_OVERVIEW__',html)
  self.assertIn(patch['label'],html)
  if patch['label']=='Preview 0.1':
   self.assertEqual(patch['install_filename'],'Bento_Preview_0.1_Install.zip')
   self.assertNotIn('1.6W22',html)
  if patch['label']=='Alpha 1.0':
   self.assertEqual(patch['install_filename'],'Bento_Alpha_1.0_Install.zip')
   self.assertNotIn('Preview 0.1',html)
   self.assertNotIn('1.6W22',html)
  self.assertEqual(sorted(p.name for p in directory.iterdir()),sorted([patch_files[0].name,'OPEN_BENTO_PATCHER.html','README.txt','patch_bento.py','LICENSE','THIRD_PARTY_NOTICES.md']))
 def test_cli_creates_verified_zip_and_refuses_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'test.zip';cmd=[sys.executable,str(directory/'patch_bento.py'),'--main',str((args.stock_dir/'bento1.bin').resolve()),'--controller',str((args.stock_dir/'bento2.bin').resolve()),'--out',str(out)]
   subprocess.run(cmd,check=True,capture_output=True);before=out.read_bytes();self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),before)
 def test_python_rejects_application_beyond_flash_bound(self):
  bad=copy.deepcopy(patch);bad['output_size']=0x1a0004
  with self.assertRaisesRegex(ValueError,'size'):apply_patch(stock,controller,bad)
 def test_synth_markers_match_generated_carriers_and_frame_ids(self):
  import base64,io,wave
  expected={'BENTO_Kick_K2.wav':144019,'BENTO_Synth_Snare.wav':144021,'BENTO_Synth_HiHat.wav':144023}
  if patch['label']!='1.6E9':expected.update({'BENTO_Synth_Clap.wav':144025,'BENTO_Synth_Tom.wav':144027,'BENTO_Synth_Subtractive.wav':144029})
  self.assertEqual(set(patch['carriers']),set(expected))
  for name,frames in expected.items():
   with wave.open(io.BytesIO(base64.b64decode(patch['carriers'][name]))) as wav:
    self.assertEqual((wav.getnframes(),wav.getframerate(),wav.getnchannels(),wav.getsampwidth()),(frames,48000,1,2))
if __name__=='__main__':unittest.main(argv=[sys.argv[0]],verbosity=2)
