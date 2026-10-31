"""Shift-free locks: isolated source compilation and native ARM widgets/routing.

No firmware image is built. BENTO_LOCK_IMAGE points to stock 1.6.1 (or the
confirmed G12); BENTO_LOCK_MANIFEST is required to undo G12's guarded patches.
The native registry, encoder slots, note selection and note
container execute unchanged. Model lookup, heap, publish/Undo storage and
repaint are fixtures. Macro/workflow sources compile unchanged to test routing.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import *

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).resolve().parent
BASE, ORIGIN = 0x08040000, 0x081E0000
MODEL, MENU, EVENT = 0x30024B00, 0x30034430, 0x20028000
DRUM, PIANO = 0xC0200000, 0xC0400000
REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]
KEEP = []


def elf(path):
    data = path.read_bytes()
    offset = struct.unpack_from("<I", data, 32)[0]
    stride, count = struct.unpack_from("<HH", data, 46)
    sections = [struct.unpack_from("<10I", data, offset + i * stride)
                for i in range(count)]
    chunks, symbols = [], {}
    for s in sections:
        if s[2] & 2 and s[1] != 8:
            chunks.append((s[3], data[s[4]:s[4] + s[5]]))
        if s[1] != 2:
            continue
        st = sections[s[6]]
        strings = data[st[4]:st[4] + st[5]]
        for i in range(0, s[5], s[9]):
            name, value, _, info, _, index = struct.unpack_from(
                "<IIIBBH", data, s[4] + i)
            if index and info & 15 == 2:
                symbols[strings[name:].split(b"\0")[0].decode()] = value & ~1
    return chunks, symbols


def compile_ui():
    out = ROOT / "build/lock-touch-check"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ui.ld").write_text(
        "SECTIONS { . = 0x081e0000; .text : { *(.text*) *(.rodata*) } "
        "/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) } }\n")
    (out / "support.c").write_text(
        "int seq_eu_active(void *v){return 0;}\n"
        "int seq_eu_grid(void *v,int b){return 0;}\n"
        "void seq_eu_header(void *v){}\n"
        "int seq_eu_encoder(void *v,unsigned k,int x){return 0;}\n"
        "void **melodic_lock_state_slot(void){return (void**)0x24048700;}\n"
        "void mel_audio_prepare(unsigned owner){}\n" +
        "void **macro_state_slot(void){return (void**)0x24048704;}\n"
        "void **macro_existing_slot(void){return (void**)0x24048704;}\n"
        "void **workflow_state_slot(void){return (void**)0x24048708;}\n"
        "int perf_macro_view(void){return 0;}\n"
        "int motion_active(int stop){return 0;}\n"
        "int perf_macro_targets(void){return 0;}\n"
        "unsigned perf_macro_focus(int set){return 0;}\n" +
        "int perf_bar_kind(void *bar){return 0;}\n"
        "int perf_point_hit(void *app,void *point,void **out){return 0;}\n"
        "int perf_bar_down(void *bar,void *point){return 0;}\n"
        "int perf_bar_up(void *bar,void *point){return 0;}\n"
        "void pg_perform_tick(void *bar,void *frame){}\n"
        "void pg_tracks_nav(void){}\n"
        "int pg_mixer_bar_drag(void *v,void *p,unsigned id,int phase){return 0;}\n" +
        "int fx_screen_active(void){return 0;}\n"
        "int fx_screen_hit(void *point,void **out){return 0;}\n"
        "void pg_fx_touch_down(void *bar,void *point){}\n"
        "void pg_fx_touch_up(void *bar,void *point){}\n" +
        "".join("int " + name + "(){__builtin_trap();}\n" for name in [
            "seq_eu_tick", "seq_eu_tab", "seq_eu_leave", "eu_clear_steps",
            "chord_toolbar", "piano_eu_toolbar", "mod_toolbar",
            "header_remove_undo", "header_sync", "seq_eu_mode",
            "header_fixed_tab", "header_fixed_action"]) +
        "extern void melodic_locks_header(),melodic_locks_event(),melodic_locks_proj(),workflow_periodic(),workflow_lock_tap();\n"
        "extern int melodic_locks_choose(void*,unsigned,unsigned);\n"
        "__attribute__((used,retain)) void *const exports[]={"
        "melodic_locks_header,melodic_locks_event,melodic_locks_proj,melodic_locks_choose,workflow_periodic,workflow_lock_tap};\n")
    command = [
        os.environ.get("BENTO_ZIG_PYTHON", "python3"), "-m", "ziglang", "cc",
        "-target", "thumb-freestanding-eabi", "-mcpu=cortex_m4",
        "-mfloat-abi=soft", "-Oz", "-g", "-ffreestanding", "-fno-builtin",
        "-fno-stack-protector", "-nostdlib", "-Wl,--entry=locks_touch",
        "-Wl,--script=" + str(out / "ui.ld"),
        str(SOURCE / "step_lock_ui.c"), str(SOURCE / "melodic_lock_ui.c"),
        str(SOURCE / "macro_ui.c"), str(SOURCE / "workflow_ui.c"),
        str(out / "support.c"), "-o", str(out / "locks.elf")]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return elf(out / "locks.elf")


def image():
    release = Path.home() / "Documents/Bento_Lab_G12_TouchRouting"
    path = Path(os.environ.get(
        "BENTO_LOCK_IMAGE", release / "01_TEST_FIRMWARE/bento1.bin"))
    data = bytearray(path.read_bytes())
    digest = hashlib.sha256(data).hexdigest()
    stock = "14475e9d5068f5659d0fe0b00fc1278c1479c43ed9fda3d40654d5f3a7a6bbb3"
    if digest != stock:
        assert digest == "838876d18a9eb2f7a81a47703b7c60f89c10b91e4ce8f45fe95a8a6dcf0dbcfc"
        manifest = json.loads(Path(os.environ.get(
            "BENTO_LOCK_MANIFEST",
            release / "04_BUILD_RECORDS/FULL_MANIFEST.json")).read_text())
        assert manifest["sha256"] == digest
        for w in reversed(manifest["writes"]):
            start = w["address"] - BASE
            replacement = bytes.fromhex(w["replacement_hex"])
            assert data[start:start + len(replacement)] == replacement
            original = bytes.fromhex(w["original_hex"])
            data[start:start + len(replacement)] = original
        data = data[:1523516]
        assert hashlib.sha256(data).hexdigest() == stock
    # Recreate only conditions.py's read-only native condition enum extension.
    start = 0x081B6000 - BASE
    pointers = bytearray(data[0x0819F30C - BASE:0x0819F30C - BASE + 400])
    labels = bytearray()
    for b in range(2, 9):
        for a in range(1, b + 1):
            pointers.extend(struct.pack("<I", BASE + start + 135 * 4 + len(labels)))
            labels.extend(f"{a}:{b}\0".encode())
    extension = pointers + labels
    data.extend(bytes(start + len(extension) - len(data)))
    data[start:start + len(extension)] = extension
    return bytes(data)


def note(step, ident, pad=2, word=0):
    return struct.pack("<BBHIIIHHI", 1, 0, pad, step * 960, 960,
                       ident, 60, 100, word)


class Fixture:
    def __init__(self, pitched=False, track_type=18):
        KEEP.append(self)
        self.pitched, self.track_type = pitched, track_type
        self.view = PIANO if pitched else DRUM
        self.owner, self.seq, self.node = 80, 77, 0xC0040000
        self.container, self.cursor = self.node + 12, 0xC0600000
        self.undo, self.published, self.emitted = [], [], []
        self.u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        self.u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M7)
        for a, n in [(BASE, 0x1C0000), (0x20000000, 0x40000),
                     (0x24000000, 0x80000), (0x30000000, 0x40000),
                     (0xC0000000, 0x800000), (0xE000E000, 0x2000)]:
            self.u.mem_map(a, n)
        self.u.mem_write(BASE, IMAGE)
        for address, data in CHUNKS:
            self.u.mem_write(address, data)
        self.u.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
        self.u.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        for i in range(7):
            self.w(0x300000CC + i * 4, 0x2001C000 + i * 32)
            self.u.mem_write(0x2001C000 + i * 32 + 9, b"\x10")
            self.w(0x2001C000 + i * 32 + 0x14, 0x081FF101)
            self.u.mem_write(0x2001C000 + i * 32 + 15, b"\1")
        self.u.mem_write(0x081FF100, bytes.fromhex("08207047"))
        addresses = [0x08104C08, 0x08133F7C, 0x08133CFC, 0x0812DFE8,
                     0x081BB080, 0x0813391A, 0x0815C27C, 0x081599BC,
                     0x0815C4B8, 0x081338DC, 0x08136544,
                     0x08173272, 0x0816FC34]
        self.hooks = [self.u.hook_add(UC_HOOK_CODE, self.hook, begin=a, end=a)
                      for a in addresses]
        self.w(0x3000004C, self.cursor)
        self.w(0x30000048, 0xC0800000)
        self.call(0x081639A8, 0)
        self.call(0x08177D48, MENU)
        self.u.mem_write(MENU + 0x30, b"\1")
        self.call(0x0815930C if pitched else 0x0815BF1C, self.view)
        self.u.mem_write(self.view + 0x30, b"\0")
        self.u.mem_write(MODEL + 0x12C, bytes([0x17 if pitched else 0x27]))
        self.w(MODEL + 0x144, self.seq)
        self.w(MODEL, 0x20002000)
        if pitched:
            for offset, value in [(0x11CD00, self.seq), (0x11CD08, self.owner)]:
                self.w(self.view + offset, value)
            self.u.mem_write(self.view + 0x125DAE, b"\0")
            self.u.mem_write(self.view + 0x125DAC, b"\0")
        else:
            for offset, value in [(0x113DC, self.container),
                                  (0x113E4, self.seq), (0x113E8, self.owner),
                                  (0x11400, 2), (0x113F8, 16)]:
                self.w(self.view + offset, value)
            self.u.mem_write(self.view + 0x113E0, b"\0")
        self.setnotes([note(0, 101, 0 if pitched else 2),
                       note(3, 102, 0 if pitched else 2),
                       note(5, 103, 0 if pitched else 3)])
        self.select([101])
        self.header()

    def w(self, a, value):
        self.u.mem_write(a, struct.pack("<I", value & 0xFFFFFFFF))

    def r(self, a):
        return struct.unpack("<I", self.u.mem_read(a, 4))[0]

    def ret(self, value=0):
        self.u.reg_write(UC_ARM_REG_R0, value & 0xFFFFFFFF)
        self.u.reg_write(UC_ARM_REG_PC, self.u.reg_read(UC_ARM_REG_LR))

    def call(self, address, *args):
        if isinstance(address, str):
            address = SYMBOLS[address]
        for reg, value in zip(REGS, args):
            self.u.reg_write(reg, value & 0xFFFFFFFF)
        self.u.reg_write(UC_ARM_REG_SP, 0x2003E000)
        self.u.reg_write(UC_ARM_REG_LR, 0x081FF001)
        try:
            self.u.emu_start(address | 1, 0x081FF000, count=3000000)
        except Exception as error:
            raise RuntimeError(f"native PC={self.u.reg_read(UC_ARM_REG_PC):08x}") from error
        assert self.u.reg_read(UC_ARM_REG_PC) == 0x081FF000
        return self.u.reg_read(UC_ARM_REG_R0)

    def hook(self, u, a, n, data):
        r = [u.reg_read(reg) for reg in REGS]
        if a == 0x08104C08:
            p = self.r(0x3000004C)
            self.w(0x3000004C, p + ((r[0] + 31) & ~31))
            self.ret(p)
        elif a == 0x08133F7C:
            self.ret((self.track_type if self.pitched else 14)
                     if self.r(r[1]) == self.owner else 24)
        elif a == 0x08133CFC:
            self.w(r[1], self.owner)
            self.ret(1)
        elif a == 0x0812DFE8:
            self.w(r[2], self.node)
            self.ret(int(r[1] == self.seq))
        elif a in (0x081BB080, 0x0813391A):
            self.ret(0)
        elif a in (0x0815C27C, 0x081599BC, 0x0815C4B8, 0x08173272):
            self.ret()
        elif a == 0x081338DC:
            self.undo.append(self.notes())
            self.ret(1)
        elif a == 0x08136544:
            self.published.append(r[2])
            if self.pitched:
                for i in range(self.r(r[2] + 0x3000)):
                    p = r[2] + i * 24
                    ident = self.r(p + 12)
                    for j, e in enumerate(self.notes()):
                        if struct.unpack_from("<I", e, 12)[0] == ident:
                            self.u.mem_write(self.container + j * 24,
                                             bytes(u.mem_read(p, 24)))
                            break
            self.ret()
        elif a == 0x0816FC34:
            ev = struct.unpack("<5I", u.mem_read(r[1], 20))
            self.emitted.append(ev)
            if ev[0] & 0xFFFF == 0xCF and r[0] in (
                    self.slot(5), self.slot(6), self.slot(7)):
                u.reg_write(UC_ARM_REG_R0, self.view)
                if self.pitched:
                    u.reg_write(UC_ARM_REG_PC, SYMBOLS["melodic_locks_event"] | 1)
                else:
                    u.reg_write(UC_ARM_REG_R1, ev[2])
                    u.reg_write(UC_ARM_REG_R2, ev[3])
                    u.reg_write(UC_ARM_REG_PC, SYMBOLS["locks_encoder"] | 1)
            else:
                self.ret()

    def setnotes(self, notes):
        self.u.mem_write(self.container, b"".join(notes))
        self.w(self.container + 0x3000, len(notes))

    def notes(self):
        return [bytes(self.u.mem_read(self.container + i * 24, 24))
                for i in range(self.r(self.container + 0x3000))]

    def select(self, ids):
        if self.pitched:
            # Native add-ID accepts only notes represented by visible grid cells.
            cells = self.r(self.view + 0x38 + 0x34)
            for i, e in enumerate(self.notes()):
                self.u.mem_write(cells + i * 0x48 + 0x31, b"\1")
                self.w(cells + i * 0x48 + 0x40,
                       struct.unpack_from("<I", e, 12)[0])
            self.call(0x08174BAC, self.view + 0x38, 0)
            for ident in ids:
                self.call(0x08174C4E, self.view + 0x38, ident, 0)
        else:
            for i in range(32):
                self.w(self.view + 0x11420 + i * 4,
                       1000 if any(struct.unpack_from("<I", e, 12)[0] in ids
                                   and struct.unpack_from("<I", e, 4)[0] == i * 960
                                   for e in self.notes()) else 0)
        self.header()

    def header(self):
        if self.pitched:
            self.call("melodic_locks_header", self.view)
        else:
            self.call("locks_header_before", self.view)
            self.call("locks_header_after", self.view)

    def slot(self, i):
        return self.view + (0x55F0 if self.pitched else 0xEBF0) + 0x38 + i * 0x468

    def key(self, i):
        return struct.unpack("<H", self.u.mem_read(self.slot(i) + 0x9C, 2))[0]

    def text(self, ptr):
        return bytes(self.u.mem_read(ptr, 80)).split(b"\0")[0].decode()

    def value(self, i, value):
        if self.pitched:
            self.u.mem_write(EVENT, struct.pack(
                "<5I", 0xCF, self.seq, self.key(i), value & 0xFFFFFFFF, 0))
            self.call("melodic_locks_event", self.view, EVENT)
        else:
            self.call("locks_encoder", self.view, self.key(i), value)
        self.header()

    def word(self, i=0):
        return struct.unpack_from("<I", self.notes()[i], 20)[0]

    def locks(self, i=0):
        return [self.call("locks_slot", self.word(i), j) for j in range(2)]

    def touch_manager(self):
        manager = 0x20030000
        app = manager + 0x470
        self.u.mem_write(manager, bytes(0x500))
        self.call(0x0816E390)
        self.call(0x0816E218, app)
        self.call(0x0816E2A0, app, self.view)
        self.call(0x0816FB64, app, self.view)
        self.u.mem_write(MENU + 0x30, b"\1")
        # Mirror only the production vtable/call-site patch locations in RAM.
        for offset, name in [(0, "macro_bar_tick"), (4, "macro_bar_down"),
                             (5, "macro_bar_move"), (6, "macro_bar_up"),
                             (7, "macro_bar_takes")]:
            self.w(0x081B2838 + offset * 4, SYMBOLS[name] | 1)
        self.w(0x081B2328, SYMBOLS["macro_app_hit"] | 1)
        at, target = 0x08163470, SYMBOLS["macro_app_hit"]
        delta = (target - at - 4) & 0x1FFFFFF
        s, i1, i2 = delta >> 24, (delta >> 23) & 1, (delta >> 22) & 1
        self.u.mem_write(at, struct.pack(
            "<HH", 0xF000 | (s << 10) | ((delta >> 12) & 0x3FF),
            0xD000 | ((1 ^ i1 ^ s) << 13) | ((1 ^ i2 ^ s) << 11)
            | ((delta >> 1) & 0x7FF)))
        self.w(0x3001FE2C, 1000)
        bar = self.slot(0) - 0x38
        self.call("macro_bar_tick", bar, EVENT)
        if not self.pitched:
            self.w(self.view + 0x11400, 2)
        self.select([101])
        return manager

    def finger(self, manager, index, down):
        report = bytearray(16)
        if down:
            struct.pack_into("<h", report, 0, 1)
            struct.pack_into("<hhB", report, 4,
                             self.r(self.slot(index) + 4) + 20,
                             self.r(self.slot(index) + 8) + 20, 1)
        self.u.mem_write(EVENT, bytes(report))
        self.call(0x0816332C, manager, EVENT)


class Tests(unittest.TestCase):
    def test_native_finger_dispatch_toggles_inline_target_without_popup(self):
        for pitched in (False, True):
            with self.subTest(pitched=pitched):
                p = Fixture(pitched)
                manager = p.touch_manager()
                before = p.notes()
                p.finger(manager, 6, True)
                p.finger(manager, 6, False)
                self.assertEqual(p.r(MENU + 0x904), 0)
                p.w(0x3001FE2C, 1301)
                p.call("workflow_periodic")
                p.header()
                self.assertEqual(p.key(6), 0x1DA)
                self.assertEqual(p.r(MENU + 0x904), 0)
                self.assertEqual(p.u.mem_read(MENU + 0x30, 1), b"\1")
                self.assertEqual(p.notes(), before)
                p.w(0x3001FE2C, 1400)
                p.finger(manager, 6, True)
                p.finger(manager, 6, False)
                p.w(0x3001FE2C, 1701)
                p.call("workflow_periodic")
                p.header()
                self.assertNotEqual(p.key(6), 0x1DA)
                self.assertEqual(p.notes(), before)

    def test_native_finger_double_tap_deletes_only_corresponding_lock(self):
        for pitched in (False, True):
            with self.subTest(pitched=pitched):
                p = Fixture(pitched)
                p.value(6, 500)
                p.value(7, 500)
                other = p.locks()[1]
                manager = p.touch_manager()
                for now in (1000, 1100):
                    p.w(0x3001FE2C, now)
                    p.finger(manager, 6, True)
                    p.finger(manager, 6, False)
                self.assertEqual(p.locks(), [0, other])
                p.w(0x3001FE2C, 1500)
                p.call("workflow_periodic")
                self.assertEqual(p.r(MENU + 0x904), 0)

    def test_native_finger_condition_slot_never_opens_popup(self):
        p = Fixture()
        manager = p.touch_manager()
        p.finger(manager, 5, True)
        p.finger(manager, 5, False)
        before = p.notes()
        p.w(0x3001FE2C, 1301)
        p.call("workflow_periodic")
        self.assertEqual(p.r(MENU + 0x904), 0)
        self.assertEqual(p.u.mem_read(MENU + 0x30, 1), b"\1")
        self.assertEqual(p.notes(), before)
        p.call(0x08171E44, p.slot(5), 12800)
        self.assertEqual(p.call("locks_condition_get", p.word()), 100)

    def test_native_finger_pending_tap_cancels_when_selection_changes(self):
        for pitched in (False, True):
            with self.subTest(pitched=pitched):
                p = Fixture(pitched)
                manager = p.touch_manager()
                p.finger(manager, 6, True)
                p.finger(manager, 6, False)
                p.select([102])
                p.w(0x3001FE2C, 1301)
                p.call("workflow_periodic")
                self.assertEqual(p.r(MENU + 0x904), 0,
                                 "workflow must compare captured locks_touch_context")

    def test_condition_touch_preserves_native_application_dispatch(self):
        p = Fixture()
        manager = p.touch_manager()
        p.finger(manager, 5, True)
        p.finger(manager, 5, False)
        p.w(0x3001FE2C, 1301)
        p.call("workflow_periodic")
        self.assertEqual(p.r(manager + 0x470), 0x081B2300)
        self.assertEqual(p.u.mem_read(MENU + 0x30, 1), b"\1")
        self.assertEqual(p.r(0x081B2330), 0x0816E195)
        self.assertEqual(p.r(0x081B2334), 0x08149409)

    def test_inline_target_changes_only_destination_then_value_encoder(self):
        for pitched in (False, True):
            with self.subTest(pitched=pitched):
                p = Fixture(pitched)
                before, keys = p.notes(), [p.key(i) for i in range(8)]
                self.assertEqual(p.call("locks_touch", p.slot(6), 0), 1)
                p.header()
                self.assertEqual(p.key(6), 0x1DA)
                p.value(6, 1)
                self.assertEqual(p.notes(), before)
                self.assertEqual(p.key(6), 0x1DA)
                p.call("locks_touch", p.slot(6), 0)
                p.header()
                self.assertEqual(p.key(6), 2)
                self.assertEqual([p.key(i) for i in range(6)], keys[:6])
                p.value(6, -6000)
                self.assertEqual(p.locks()[0], 0x51010384)
                self.assertEqual(p.u.mem_read(MENU + 0x30, 1), b"\1")

    def test_native_target_encoder_keeps_other_lock_in_value_mode(self):
        for pitched in (False, True):
            for which in (0, 1):
                with self.subTest(pitched=pitched, which=which):
                    p = Fixture(pitched)
                    index = 6 + which
                    other = p.key(7 - which)
                    before = p.notes()
                    p.call("locks_touch", p.slot(index), 0)
                    p.header()
                    self.assertEqual(p.key(index), 0x1E4 if which else 0x1DA)
                    self.assertEqual(p.key(7 - which), other)
                    p.call(0x08171E44, p.slot(index), 12800)
                    p.header()
                    self.assertEqual(p.notes(), before)
                    self.assertEqual(p.emitted[-1][2], p.key(index))
                    self.assertEqual(p.r(MENU + 0x904), 0)

    def test_changing_target_never_changes_partner_target(self):
        for which, duplicate in ((0, 4), (1, 1)):
            with self.subTest(which=which):
                p = Fixture()
                partner_key = p.key(7 - which)
                self.assertEqual(p.call("locks_touch", p.slot(6 + which), 0), 1)
                p.header()
                picker_key = p.key(6 + which)
                self.assertIn(picker_key, (0x1DA, 0x1E4))

                p.call("locks_encoder", p.view, picker_key, duplicate)
                p.header()
                self.assertEqual(p.key(7 - which), partner_key)
                for target in range(12):
                    p.call("locks_encoder", p.view, picker_key, target)
                    p.header()
                    self.assertEqual(p.key(7 - which), partner_key)

    def test_inline_remove_choice_commits_only_on_return_to_value(self):
        for pitched in (False, True):
            p = Fixture(pitched)
            p.value(6, 500)
            p.value(7, 500)
            before, other, undos = p.notes(), p.locks()[1], len(p.undo)
            p.call("locks_touch", p.slot(6), 0)
            p.header()
            p.value(6, 0)
            self.assertEqual(p.notes(), before)
            p.call("locks_touch", p.slot(6), 0)
            p.header()
            self.assertEqual(p.locks(), [0, other])
            self.assertEqual(len(p.undo), undos + 1)

    def test_double_tap_while_choosing_exits_and_keeps_partner(self):
        for pitched in (False, True):
            p = Fixture(pitched)
            p.value(6, 500)
            p.value(7, 500)
            other = p.locks()[1]
            p.call("locks_touch", p.slot(6), 0)
            p.header()
            p.call("locks_touch", p.slot(6), 1)
            p.header()
            self.assertNotEqual(p.key(6), 0x1DA)
            self.assertEqual(p.locks(), [0, other])

    def test_double_tap_deletes_only_selected_slot_and_keeps_native_metadata(self):
        for pitched in (False, True):
            for which in (0, 1):
                with self.subTest(pitched=pitched, which=which):
                    p = Fixture(pitched)
                    p.select([101, 102])
                    p.value(6, 500 if pitched else -6000)
                    p.value(7, 750 if pitched else 600)
                    before, locks = p.notes(), p.locks()
                    undos = len(p.undo)
                    p.call("locks_touch", p.slot(6 + which), 1)
                    self.assertEqual(p.locks()[which], 0)
                    self.assertEqual(p.locks()[1 - which], locks[1 - which])
                    self.assertEqual(p.locks(1)[which], 0)
                    self.assertEqual(p.notes()[2], before[2])
                    self.assertEqual([e[:20] for e in p.notes()],
                                     [e[:20] for e in before])
                    self.assertEqual(len(p.undo), undos + 1)
                    self.assertEqual(p.undo[-1], before)

    def test_inline_condition_preserves_pair_and_survives_lock_deletion(self):
        p = Fixture()
        p.value(6, -6000)
        p.value(7, 400)
        before = p.notes()
        p.value(5, 103)
        self.assertEqual(p.undo, [before])
        condition = p.call("locks_condition_get", p.word())
        self.assertGreaterEqual(condition, 100)
        other = p.locks()[1]
        p.call("locks_touch", p.slot(6), 1)
        self.assertEqual(p.call("locks_condition_get", p.word()), condition)
        self.assertEqual(p.locks(), [0, other])
        p.call("locks_touch", p.slot(7), 1)
        self.assertEqual(p.locks(), [0, 0])
        self.assertEqual(p.call("locks_condition_get", p.word()), condition)

    def test_inline_condition_without_selection_or_memory_is_atomic(self):
        for selected in (False, True):
            p = Fixture()
            if selected:
                p.w(0x30000048, p.r(0x3000004C))
            else:
                p.select([])
            before, undos = p.notes(), len(p.undo)
            p.call("locks_encoder", p.view, 0x199, 103)
            p.header()
            self.assertEqual(p.notes(), before)
            self.assertEqual(len(p.undo), undos)
            self.assertEqual(p.u.mem_read(MENU + 0x30, 1), b"\1")

    def test_context_signature_changes_on_selection_page_or_track(self):
        for pitched in (False, True):
            with self.subTest(pitched=pitched):
                p = Fixture(pitched)
                signature = p.call("locks_touch_context", p.slot(6))
                self.assertNotEqual(signature, 0)
                p.select([102])
                self.assertNotEqual(p.call("locks_touch_context", p.slot(6)), signature)
                p.w(p.view + (0x11CD08 if pitched else 0x113E8), p.owner + 1)
                self.assertEqual(p.call("locks_touch_context", p.slot(6)), 0)
                p.u.mem_write(MODEL + 0x12C, b"\x02")
                self.assertEqual(p.call("locks_touch_supported", p.slot(6)), 0)

    def test_selection_change_exits_inline_target_mode(self):
        for pitched in (False, True):
            with self.subTest(pitched=pitched):
                p = Fixture(pitched)
                key = p.key(6)
                p.call("locks_touch", p.slot(6), 0)
                p.header()
                self.assertEqual(p.key(6), 0x1DA)
                p.select([102])
                before = p.notes()
                if pitched:
                    p.call("melodic_locks_choose", p.view, 0x1DA, 1)
                else:
                    p.call("locks_encoder", p.view, 0x1DA, 1)
                p.header()
                self.assertEqual(p.notes(), before)
                self.assertEqual(p.key(6), key)
                self.assertEqual(p.u.mem_read(MENU + 0x30, 1), b"\1")

    def test_supported_slots_and_no_melodic_condition(self):
        for pitched in (False, True):
            p = Fixture(pitched)
            self.assertEqual([p.call("locks_touch_supported", p.slot(i))
                              for i in range(8)],
                             [0, 0, 0, 0, 0, 0 if pitched else 1, 1, 1])
            self.assertEqual(p.call("locks_touch_supported", p.slot(6) + 4), 0)
            p.u.mem_write(p.slot(6) + 0x30, b"\1")
            self.assertEqual(p.call("locks_touch_supported", p.slot(6)), 0)

    def test_proj_is_noop_and_never_switches_encoder_keys_or_removes_locks(self):
        for pitched in (False, True):
            p = Fixture(pitched)
            p.value(6, 500)
            before, keys = p.notes(), [p.key(i) for i in range(8)]
            for down in (1, 0):
                p.call("locks_proj", MODEL, down)
                p.call("melodic_locks_proj", MODEL, down)
                p.header()
            self.assertEqual(p.notes(), before)
            self.assertEqual([p.key(i) for i in range(8)], keys)

    def test_limited_melodic_choices_exclude_sampler_attack_pitch_and_sustain(self):
        p = Fixture(True)
        p.call("locks_touch", p.slot(7), 0)
        p.header()
        descriptor = p.r(0x30031484) + 0x1E4 * 32
        labels = [p.text(p.r(p.r(descriptor + 8) + i * 4))
                  for i in range(p.r(descriptor + 12))]
        for title in ("Attack", "Pitch", "Sustain"):
            self.assertNotIn(title, labels)
        self.assertIn("Reverb Send", labels)

    def test_native_value_encoder_emits_unchanged_cf_event(self):
        for pitched in (False, True):
            p = Fixture(pitched)
            p.value(6, 500 if pitched else -6000)
            before, key = p.word(), p.key(6)
            p.call(0x08171E44, p.slot(6), 1024)
            self.assertNotEqual(p.word(), before)
            self.assertEqual(p.key(6), key)
            self.assertEqual(p.emitted[-1][0] & 0xFFFF, 0xCF)
            self.assertEqual(p.emitted[-1][2], key)

    def test_no_selection_or_no_memory_does_not_mutate_notes(self):
        for pitched in (False, True):
            p = Fixture(pitched)
            p.value(6, 500)
            p.select([])
            before = p.notes()
            p.call("locks_touch", p.slot(6), 1)
            self.assertEqual(p.notes(), before)
            p.w(0x30000048, p.r(0x3000004C))
            p.call("locks_touch", p.slot(6), 0)
            self.assertEqual(p.notes(), before)
            self.assertEqual(p.r(MENU + 0x904), 0)

    def test_all_conditions_are_reachable_with_native_inline_encoder(self):
        p = Fixture()
        before = p.notes()
        p.value(5, 0)
        for value in range(135):
            if value:
                p.call(0x08171E44, p.slot(5), 12800)
                p.header()
            self.assertEqual(p.r(p.slot(5) + 0xA0), value)
            self.assertEqual(p.call("locks_condition_get", p.word()),
                             0 if value == 99 else value + 1 if value < 99 else value)
            self.assertEqual(p.locks(), [0, 0])
            self.assertEqual([e[:20] for e in p.notes()], [e[:20] for e in before])
            self.assertEqual(p.notes()[1:], before[1:])
            self.assertEqual(p.r(MENU + 0x904), 0)
            self.assertEqual(p.u.mem_read(MENU + 0x30, 1), b"\1")

    def test_picker_does_not_duplicate_other_occupied_lock(self):
        for pitched in (False, True):
            p = Fixture(pitched)
            p.value(7, 500)
            before, key = p.notes(), p.key(6)
            p.call("locks_touch", p.slot(6), 0)
            p.header()
            p.value(6, 4)
            p.call("locks_touch", p.slot(6), 0)
            p.header()
            self.assertEqual(p.notes(), before)
            self.assertEqual(p.key(6), key)


def setUpModule():
    global IMAGE, CHUNKS, SYMBOLS
    IMAGE = image()
    try:
        CHUNKS, SYMBOLS = compile_ui()
    except subprocess.CalledProcessError as error:
        print(error.stdout, error.stderr)
        raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
