"""R6.18 lean black box on the built image (BENTO_FX_CANDIDATE).

Runs the shipped bytes in the emulator: the patched M4 startup stub (081004B6,
which must call bb_boot and then reach the K16 startup 081B5200 with every
register restored) and the three patched card sites (project save 0813044C
around the writer 08130958; document reader 08130A18 at 08130522/08130774).
Only stock FatFS (f_open 08120148, f_write 08120604, f_close 08120974), the
chained stock writer/reader and the RTC backup registers are fixtures.
Cases: boot generation, junk in reset-surviving RAM, record present/absent,
a new crash, no card, full card, nothing new = no card access."""
import json, os, re, struct, unittest
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import *

R = Path(__file__).resolve().parent
CANDIDATE = Path(os.environ.get('BENTO_FX_CANDIDATE', R.parents[1] / 'tf2_candidate'))
IMAGE = (CANDIDATE / 'bento1.bin').read_bytes()
UU = json.loads((CANDIDATE / 'manifest.json').read_text())['ui_symbols']
BASE = 0x08040000
STATE, FIL, LINE = 0x24048810, 0x24048840, 0x240488a0
BKP = 0x58004050
F_OPEN, F_WRITE, F_CLOSE = 0x08120148, 0x08120604, 0x08120974
WRITER, READER = 0x08130958, 0x08130a18
SITES = [(0x0813044c, WRITER), (0x08130522, READER), (0x08130774, READER)]
STOP = 0x081ff000
GPR = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5,
       UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
       UC_ARM_REG_R12]


def label():
    ptr = struct.unpack_from('<I', IMAGE, 0x08131054 - BASE)[0]
    o = ptr - BASE
    return IMAGE[o:IMAGE.index(b'\0', o)].decode()


class Device:
    def __init__(self, junk=False):
        u = self.u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M7)
        for a, n in [(0x08000000, 0x200000), (0x24000000, 0x80000), (0x30000000, 0x40000), (0x58004000, 0x1000)]:
            u.mem_map(a, n)
        u.mem_write(BASE, IMAGE)
        u.reg_write(UC_ARM_REG_C1_C0_2, 0xf << 20); u.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        if junk:  # power-up pattern in the reset-surviving area
            u.mem_write(0x24048800, bytes((i * 37 + 11) & 255 for i in range(0x260)))
        self.w(0x3001fe2c, 8123)
        self.w(0x58004000, 0x00142233); self.w(0x58004004, 0x00261110)  # RTC TR/DR (BCD)
        self.file = b''; self.calls = []; self.present = True; self.space = 1 << 20; self.open = False
        self.chained = []
        u.hook_add(UC_HOOK_CODE, self.hook)

    def w(self, a, v): self.u.mem_write(a, struct.pack('<I', v & 0xffffffff))
    def r(self, a): return struct.unpack('<I', self.u.mem_read(a, 4))[0]
    def bkp(self, words):
        for i, v in words.items(): self.w(BKP + 4 * i, v)

    def ret(self, value):
        self.u.reg_write(UC_ARM_REG_R0, value)
        self.u.reg_write(UC_ARM_REG_PC, self.u.reg_read(UC_ARM_REG_LR) | 1)

    def cstr(self, a):
        b = bytes(self.u.mem_read(a, 64)); return b[:b.index(b'\0')].decode()

    def hook(self, u, address, size, _):
        a = [u.reg_read(r) for r in GPR[:4]]
        if address == F_OPEN:
            self.calls.append(('open', a[0], self.cstr(a[1]), a[2]))
            if not self.present: return self.ret(3)  # FR_NOT_READY
            self.open = True; return self.ret(0)
        if address == F_WRITE:
            data = bytes(u.mem_read(a[1], a[2])); n = min(len(data), self.space)
            self.calls.append(('write', a[0], data)); self.file += data[:n]; self.space -= n
            self.w(a[3], n); return self.ret(0)
        if address == F_CLOSE:
            self.calls.append(('close', a[0])); self.open = False; return self.ret(0)
        if address in (WRITER, READER):
            self.chained.append((address, a)); return self.ret(0x55)
        if address == STOP: u.emu_stop()

    def run(self, pc, until, regs=None, sp=0x30038000):
        u = self.u
        for i, r in enumerate(GPR): u.reg_write(r, (regs or {}).get(i, 0x1000 + i))
        u.reg_write(UC_ARM_REG_SP, sp); u.reg_write(UC_ARM_REG_LR, STOP | 1)
        self.stop_at = until
        h = u.hook_add(UC_HOOK_CODE, lambda uc, a, s, d: uc.emu_stop(), begin=until, end=until)
        u.emu_start(pc | 1, STOP, count=2_000_000)
        u.hook_del(h)
        assert u.reg_read(UC_ARM_REG_PC) == until, hex(u.reg_read(UC_ARM_REG_PC))

    def boot(self):
        before = {i: 0x1000 + i for i in range(13)}
        self.run(0x081004b6, 0x081b5200, before)
        got = [self.u.reg_read(r) for r in GPR]
        assert got == [0x1000 + i for i in range(13)], 'startup stub must restore all registers'
        assert self.u.reg_read(UC_ARM_REG_SP) == 0x30038000

    def card(self, site=0):
        at, orig = SITES[site]
        regs = {i: 0x2000 + i for i in range(13)}
        self.run(at, at + 4, regs)
        assert self.u.reg_read(UC_ARM_REG_R0) == 0x55, 'stock result returned unchanged'
        for i in range(4, 12): assert self.u.reg_read(GPR[i]) == 0x2000 + i, ('callee-saved', i)
        assert self.chained[-1][0] == orig and self.chained[-1][1][:4] == [0x2000, 0x2001, 0x2002, 0x2003]
        assert self.u.reg_read(UC_ARM_REG_SP) == 0x30038000

    def state(self): return [self.r(STATE + 4 * i) for i in range(6)]
    def lines(self): return self.file.decode().splitlines()


class BlackBox(unittest.TestCase):
    def test_sites_are_wired_and_chain_stock(self):
        for at, orig in SITES:
            h1, h2 = struct.unpack_from('<HH', IMAGE, at - BASE)
            self.assertEqual((h1 & 0xf800, h2 & 0xd000), (0xf000, 0xd000), hex(at))
        d = Device(); d.boot()
        for s in range(3): d.card(s)
        self.assertEqual(len([c for c in d.calls if c[0] == 'open']), 1)  # boot line once

    def test_boot_line_format_and_generation(self):
        d = Device(); d.boot(); d.card()
        opens = [c for c in d.calls if c[0] == 'open']
        self.assertEqual(opens, [('open', FIL, '\\BENTO_CRASHES.log', 0x32)])
        self.assertEqual(d.calls[-1], ('close', FIL))
        self.assertEqual(d.lines(), ['boot gen=1 fw=%s rtc=261110-142233 ms=8123 count=0 state=fresh' % label()])
        d.file = b''; d.boot(); d.boot(); d.card()   # a boot without card access leaves a gap
        self.assertEqual(d.lines(), ['boot gen=3 fw=%s rtc=261110-142233 ms=8123 count=0 state=kept' % label()])
        n = len(d.calls); d.card(1); d.card(2); d.card(0)
        self.assertEqual(len(d.calls), n, 'nothing new: no card access')

    def test_junk_ram_gives_fresh_state_and_no_card_access_before_boot(self):
        d = Device(junk=True)
        d.card()
        self.assertEqual(d.calls, [], 'junk state is never trusted')
        d.boot(); s = d.state()
        self.assertEqual(s[:4], [0x31584242, 1, 0, 3])
        d.card(); self.assertIn('state=fresh', d.lines()[0])

    # The pc/lr samples below are data, not native addresses: written as int('..', 16) so that the
    # 1.6.8 tree translation does not rewrite them (the expected text keeps the same digits).
    def test_existing_record_on_fresh_state(self):
        d = Device(); d.bkp({i: 0x1111 * i for i in range(32)})
        d.bkp({24: 5, 25: 1, 27: 2, 12: int('0805abcd', 16), 31: int('0805abcd', 16), 11: int('0805a001', 16)})  # the native fault recorder stores the pc in [12] and [31] (0804B3D4, 0804B416)
        d.boot(); d.card()
        rec, boot = d.lines()
        self.assertTrue(rec.startswith('record gen=1 count=5 cause=00000001 core=00000002 pc=0805abcd lr=0805a001 bkp='), rec)
        words = rec.split('bkp=')[1].split(',')
        self.assertEqual(len(words), 32); self.assertEqual(int(words[24], 16), 5); self.assertEqual(int(words[3], 16), 0x3333)
        self.assertTrue(boot.startswith('boot gen=1 ') and boot.endswith('count=5 state=fresh'), boot)
        self.assertLess(len(rec), 0x1a0)
        d.file = b''; d.boot(); d.card()
        self.assertEqual(len(d.lines()), 1, 'the logged record is not repeated')

    def test_no_record_on_fresh_state(self):
        d = Device(); d.boot(); d.card()
        self.assertEqual(len(d.lines()), 1)

    def test_new_crash_after_reset_and_mid_session(self):
        d = Device(); d.boot(); d.card()
        d.bkp({24: 1, 25: 3, 27: 1, 12: int('08123456', 16), 31: int('08123456', 16), 11: int('08100001', 16)}); d.boot(); d.file = b''; d.card()
        crash, boot = d.lines()
        self.assertTrue(crash.startswith('crash gen=2 count=1 cause=00000003 core=00000001 pc=08123456'), crash)
        self.assertTrue(boot.startswith('boot gen=2 ') and boot.endswith('count=1 state=kept'))
        d.file = b''; d.bkp({24: 2}); d.card(2)  # mid-session record (M4 still running)
        self.assertEqual(len(d.lines()), 1); self.assertTrue(d.lines()[0].startswith('crash gen=2 count=2 '))
        d.file = b''; d.card(); self.assertEqual(d.file, b'')

    def test_native_watchdog_record_shows_the_interrupted_pc_and_which_thread_timed_out(self):
        # P168 exp3. Owner's log: every "crash" line said pc=08056f4c lr=100451bc, on two firmware versions.
        # Those lines are cause 5 = the native M4 watchdog recorder (08107AE8, entered from the WWDG vector),
        # which stores only the interrupted pc ([31]) and a few words; [12]/[11] stay from an older fault.
        # The record is produced here by that native recorder itself, on top of an older fault record.
        d = Device(); d.u.mem_map(0xe000e000, 0x1000)
        stale = {4: 0xc1000004, 5: 0x8600, 11: int('100451bc', 16), 12: int('08056f4c', 16), 22: 0x2404cb10, 31: int('08056f4c', 16)}
        d.bkp({0: 3, 24: 405, 25: 1, 27: 2}); d.bkp(stale); d.boot(); d.card(); d.file = b''
        watchdog = 0x3000f624  # native monitor 081082F8: +0 file thread report, +4 main thread report, +8 tick
        d.w(watchdog + 8, 20000); d.w(watchdog + 4, 20000 - 3400); d.w(watchdog, 20000 - 120)
        frame = 0x30030000; interrupted = int('0811f5b1', 16) - 1
        d.u.mem_write(frame, struct.pack('<8I', 1, 2, 3, 4, 5, 6, interrupted, 0x61000000))
        for reg, v in zip(GPR, [frame, 0xffffffed, 0x30039088, frame]): d.u.reg_write(reg, v)
        d.u.reg_write(UC_ARM_REG_SP, 0x30038000); d.u.reg_write(UC_ARM_REG_LR, STOP | 1)
        reset = 0x08107834  # native system reset, called by the recorder when the record is stored
        h = d.u.hook_add(UC_HOOK_CODE, lambda uc, a, n, _: uc.emu_stop(), begin=reset, end=reset)
        d.u.emu_start(0x08107ae8 | 1, STOP, count=2_000_000); d.u.hook_del(h)
        self.assertEqual(d.u.reg_read(UC_ARM_REG_PC), reset)
        self.assertEqual([d.r(BKP + 4 * i) for i in (24, 25, 27, 31)], [406, 5, 1, interrupted])  # what the native recorder wrote
        self.assertEqual(d.r(BKP + 4 * 12), stale[12])                                             # and what it left
        d.boot(); d.card()
        crash = d.lines()[0]
        self.assertTrue(crash.startswith('crash gen=2 count=406 cause=00000005 core=00000001 pc=0811f5b0 '), crash)
        words = [int(w, 16) for w in crash.split('bkp=')[1].split(',')]
        self.assertEqual(words[22], 120 << 16 | 3400)  # file thread 120 ticks, main thread 3400 (> 3332: "Main Timed Out")

    def test_no_card_gives_up_after_two_attempts(self):
        d = Device(); d.boot(); d.present = False
        for s in (0, 1, 2, 0): d.card(s)
        self.assertEqual([c[0] for c in d.calls], ['open', 'open'])
        self.assertEqual(d.state()[4], 2)
        d.present = True; d.boot(); d.card(0)
        self.assertEqual(len(d.lines()), 1, 'next boot writes its own line')

    def test_full_card_keeps_pending_and_closes(self):
        d = Device(); d.boot(); d.space = 10; d.card(0)
        self.assertEqual([c[0] for c in d.calls], ['open', 'write', 'close'])
        self.assertEqual(d.state()[3] & 1, 1, 'boot line still pending'); self.assertEqual(d.state()[4], 1)
        d.space = 1 << 20; d.file = b''; d.card(1)
        self.assertEqual(len(d.lines()), 1)
        self.assertEqual(d.state()[3] & 1, 0)

    def test_state_only_touches_its_reserved_ram(self):
        d = Device(junk=True); before = bytes(d.u.mem_read(0x24048800, 0x280))
        d.boot(); d.card()
        after = bytes(d.u.mem_read(0x24048800, 0x280))
        changed = [i for i in range(0x280) if before[i] != after[i]]
        # P168 exp7: 24048A40..24048A5F is the card request box of kick_ui.c (CardBox); bb_boot clears it at every
        # startup. The T2 counters from 24048A60 on stay untouched.
        self.assertTrue(all(0x10 <= i < 0x260 for i in changed), [hex(0x24048800 + i) for i in changed[:4]])
        self.assertEqual(after[0x240:0x260], bytes(0x20))


if __name__ == '__main__':
    unittest.main()
