"""Offline Bento patcher; Python standard library only. Never flashes devices."""
from pathlib import Path
import argparse,base64,hashlib,json,zipfile

def sha(data):return hashlib.sha256(data).hexdigest()
def apply_patch(stock,controller,manifest):
 if manifest.get('format')!='bento-delta-v1':raise ValueError('Unsupported patch format')
 if len(stock)!=manifest['input_size'] or sha(stock)!=manifest['input_sha256']:raise ValueError('Main firmware is not the exact supported original Bento 1.6.1 file')
 if sha(controller)!=manifest['controller_sha256']:raise ValueError('Controller firmware is not the supported original file')
 size=manifest['output_size']
 if not len(stock)<=size<=0x1a0000 or size%4:raise ValueError('Invalid application image size')
 result=bytearray(size);result[:len(stock)]=stock;end=0
 for offset,encoded in manifest['writes']:
  data=base64.b64decode(encoded,validate=True)
  if offset<end or offset<0 or offset+len(data)>size:raise ValueError('Overlapping or out-of-range patch')
  result[offset:offset+len(data)]=data;end=offset+len(data)
 if sha(result)!=manifest['output_sha256']:raise ValueError('Patched firmware verification failed; no output created')
 return bytes(result)
def make_zip(stock,controller,result,manifest):
 import io
 readme=f"""Bento {manifest['label']} experimental test

1. Back up your projects. Keep the original firmware pair.
2. Copy BOTH files from 01_TEST_FIRMWARE to the microSD root.
3. If needed, copy the WAV loading markers from 02_SD_CONTENT/Projects into Projects.
4. Use Bento's normal SD firmware update procedure. Confirm {manifest['label']} on the device.
5. To restore, copy BOTH files from 03_STOCK_RESTORE to the SD root and use the same procedure.

The WAV files are silent engine selectors, not playable sample packs.
The patcher runs locally and never connects to or flashes a device.
The controller file is copied unchanged. This package contains application firmware only;
the original bootloader is not patched. Hardware validation of this release remains pending.

Main SHA-256: {manifest['output_sha256']}
"""
 files={'00_START_HERE.txt':readme.encode(),'01_TEST_FIRMWARE/bento1.bin':result,'01_TEST_FIRMWARE/bento2.bin':controller,'03_STOCK_RESTORE/bento1.bin':stock,'03_STOCK_RESTORE/bento2.bin':controller}
 for name,encoded in manifest['carriers'].items():
  if '/' in name or '\\' in name or not name.endswith('.wav'):raise ValueError('Invalid synth marker name')
  files['02_SD_CONTENT/Projects/'+name]=base64.b64decode(encoded,validate=True)
 if manifest.get('source_url'):files['SOURCE.txt']=(manifest['source_url']+'\nProject additions: GPL-3.0-or-later; vendored code retains its licenses.\n').encode()
 files['SHA256SUMS.txt']=''.join(sha(data)+'  '+name+'\n' for name,data in sorted(files.items())).encode()
 output=io.BytesIO()
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
  for name,data in files.items():z.writestr(name,data)
 return output.getvalue()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--main',type=Path,required=True);p.add_argument('--controller',type=Path,required=True);p.add_argument('--patch',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 try:
  patch=a.patch
  if patch is None:
   candidates=sorted(Path(__file__).parent.glob('*.patch.json'))
   if len(candidates)!=1:raise ValueError('Choose exactly one patch with --patch')
   patch=candidates[0]
  manifest=json.loads(patch.read_text());stock=a.main.read_bytes();controller=a.controller.read_bytes();result=apply_patch(stock,controller,manifest);data=make_zip(stock,controller,result,manifest)
  # Never overwrite an input, existing ZIP, or previous output.
  with a.out.open('xb') as f:f.write(data)
 except (OSError,ValueError,KeyError,TypeError) as e:p.exit(1,str(e)+'\n')
 print('Verified',manifest['label'],'— created',a.out)
if __name__=='__main__':main()
