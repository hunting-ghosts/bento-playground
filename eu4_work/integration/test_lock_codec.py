"""Check single-pass pair decoding against the frozen native-word encoding."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest


class LockCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        root=Path(cls.temp.name)
        source=root/"codec.c"
        header=Path(__file__).resolve().parent/"step_lock_shared.h"
        source.write_text(f'#include "{header}"\n'
                          'void decode(unsigned word,unsigned *a,unsigned *b){lock_slots(word,a,b);}\n'
                          'unsigned encode(unsigned a,unsigned b){return pack_locks(a,b);}\n'
                          'int present(unsigned word){return has_locks(word);}\n')
        library=root/"codec.so"
        subprocess.run(["cc","-shared","-fPIC","-O2",str(source),"-o",str(library)],check=True)
        cls.lib=ctypes.CDLL(str(library))
        cls.lib.decode.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.POINTER(ctypes.c_uint32)]
        cls.lib.encode.argtypes=[ctypes.c_uint32,ctypes.c_uint32]
        cls.lib.encode.restype=ctypes.c_uint32
        cls.lib.present.argtypes=[ctypes.c_uint32]

    def decode(self,word):
        a,b=ctypes.c_uint32(),ctypes.c_uint32()
        self.lib.decode(word,ctypes.byref(a),ctypes.byref(b))
        return a.value,b.value

    def test_all_legacy_and_extended_pair_boundaries_match_frozen_encoding(self):
        counts=[1,1081,48001,2001,2001]+[1001]*7+[156]+[101]*17+[1001]*2
        groups=[]
        for extended in (False,True):
            for a in range(30 if extended else 12):
                for b in range(12 if extended and a<=11 else 0,30 if extended else 12):
                    if (a and a==b) or (extended and a<=11 and b<=11):continue
                    groups.append((a,b))
        self.assertEqual(sum(counts[a]*counts[b] for a,b in groups),1519176901)
        for a in range(32):
            for b in range(30 if a<30 else 0,32):
                if a!=b:groups.append((a,b))
        base=0
        for a,b in groups:
            for va,vb in ((0,0),(counts[a]-1,0),(0,counts[b]-1),(counts[a]-1,counts[b]-1)):
                first=0x51000000|(a<<16)|va if a else 0
                second=0x51000000|(b<<16)|vb if b else 0
                word=0x80000000|base+va*counts[b]+vb
                with self.subTest(a=a,b=b,va=va,vb=vb):
                    self.assertEqual(self.decode(word),(first,second))
                    if b:self.assertEqual(self.lib.encode(first,second),word)
                    self.assertEqual(bool(self.lib.present(word)),bool(a or b))
            base+=counts[a]*counts[b]

    def test_empty_single_and_invalid_words(self):
        for word,expected in ((0,(0,0)),(0x5101030c,(0x5101030c,0)),
                              (0x5101ffff,(0,0)),(0xffffffff,(0,0))):
            self.assertEqual(self.decode(word),expected)


if __name__=="__main__":
    unittest.main()
