"""Syncussion save/load adapters with native XML nodes and attributes.

The allocator and project/model services are fixtures. This does not reproduce
the owner's immediate Save As reset or exercise the complete SD save worker.
"""
import struct
import unittest

from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R6

from test_drum_motion import DrumPage, VIEW, FILTER, KEYS
from test_perf import EV, OUT
from test_integration import IMAGE

DOC, OBJECT, NAME = 0xc0180000, 0x20010000, 0x20012000


class NativeXml(DrumPage):
    def __init__(self, engine=15):
        super().__init__(engine)
        for hook in self.h[7:12]:
            self.u.hook_del(hook)
        # Native CRT copies 081B3E38..081B3F3C to 30000000..30000104.
        # Restore just its locale object; leave the active fixture heap intact.
        start = 0x081b3e38 + 0xf0 - 0x08040000
        self.u.mem_write(0x300000f0, IMAGE[start:start + 0x14])
        counter = struct.unpack_from("<I", IMAGE, 0x0812d8d0 - 0x08040000)[0]
        self.w(counter, 0x10000)
        self.xml_allocations = []

        def allocate(u, address, size, data):
            count = u.reg_read(UC_ARM_REG_R0)
            # Native 08104C58 returns block+16 with [block+12] == the result.
            pointer = self.next + 16
            self.w(pointer - 4, pointer)
            self.next += 32 + ((count + 31) & ~31)
            self.xml_allocations.append((pointer, count))
            self.w(0x3000004c, self.next)
            self.ret(pointer)

        self.u.hook_add(UC_HOOK_CODE, allocate, begin=0x08104c58, end=0x08104c58)
        self.call(0x0810a0c0, DOC, 1, 0)
        self.u.mem_write(NAME, b"cell\0")
        self.node = self.call(0x0810a316, DOC, NAME)
        self.call(0x08109412, DOC, self.node)
        self.u.mem_write(NAME, b"params\0")
        self.params = self.call(0x0810a316, DOC, NAME)
        self.call(0x08109412, self.node, self.params)
        self.u.mem_write(OBJECT, bytes(32))
        self.u.mem_write(OBJECT + 4, b"\1")
        self.w(OBJECT + 0x10, FILTER)

    def attribute(self, key):
        self.u.mem_write(NAME, key.encode() + b"\0")
        attr = self.call(0x08109c64, self.params, NAME)
        if not attr:
            return None
        self.w(OUT, 0xdead)
        if self.call(0x08109566, attr, OUT):
            raise AssertionError("Native XML integer parse failed: " + key)
        return self.r(OUT)

    def edit(self, key, value):
        self.u.mem_write(EV, struct.pack("<5I", 0xcf, FILTER, key, value, 0))
        self.call(self.symbol("kick_ui_event"), VIEW, EV)

    def clone(self, object=OBJECT):
        def pool_allocate(u, address, size, data):
            count = u.reg_read(UC_ARM_REG_R1)
            pointer = self.next
            self.next += max(32, (count + 31) & ~31)
            self.w(u.reg_read(UC_ARM_REG_R2), pointer)
            self.ret(1)

        hook = self.u.hook_add(UC_HOOK_CODE, pool_allocate,
                               begin=0x08101fb4, end=0x08101fb4)
        try:
            if self.call(0x0812e3c0, object, 0xc0190000, OUT) != 1:
                raise AssertionError("Native cell clone failed")
            return self.r(OUT)
        finally:
            self.u.hook_del(hook)

    def save(self, object=OBJECT):
        self.u.reg_write(UC_ARM_REG_R6, object)
        hook = self.u.hook_add(UC_HOOK_CODE, lambda *args: self.ret(),
                               begin=0x0812f5ee, end=0x0812f5ee)
        try:
            self.call(0x0812f5ea, self.params)
        finally:
            self.u.hook_del(hook)

    def load(self):
        hook = self.u.hook_add(UC_HOOK_CODE, lambda *args: self.ret(),
                               begin=0x0812fab0, end=0x0812fab0)
        try:
            self.call(0x0812faac, self.node, OBJECT)
        finally:
            self.u.hook_del(hook)


class Tests(unittest.TestCase):
    def test_native_save_snapshot_clone_retains_syncussion_settings(self):
        p = NativeXml()
        for key, value in zip(KEYS, (160, 82, 73, 64, 55, 46, 37, 28)):
            p.edit(key, value)
        p.u.mem_write(0x24043d80, b"\x66")
        p.u.mem_write(0x2404352f, b"\xff")
        cloned = p.clone()
        self.assertNotEqual(p.r(cloned + 0x10), FILTER)
        p.save(cloned)
        self.assertEqual(p.attribute("bento_drum_model"), 15)
        self.assertEqual(p.attribute("bento_kick_v1_tune"), 160)
        self.assertEqual(p.attribute("bento_syncussion_attack"), 28)
        self.assertEqual(p.attribute("bento_drum_v2_click"), 102)
        self.assertEqual(p.attribute("bento_mod_engine"), 15)

    def test_native_snapshot_preserves_every_drum_family_and_sample_child_type(self):
        for model in (1, 3, 5, 7, 9, 15):
            for kind in (1, 2):
                with self.subTest(engine=model, kind=kind):
                    p = NativeXml(model)
                    p.u.mem_write(OBJECT + 4, bytes([kind]))
                    p.edit(KEYS[1], 82)
                    p.save(p.clone())
                    self.assertEqual(p.attribute("bento_drum_model"), model)
                    self.assertEqual(p.attribute("bento_kick_v1_decay"), 82)

    def test_native_snapshot_is_frozen_and_copy_of_copy_retains_settings(self):
        p = NativeXml()
        p.edit(KEYS[0], 160)
        p.edit(KEYS[7], 28)
        cloned = p.clone()
        p.edit(KEYS[0], 90)
        p.edit(KEYS[7], 75)
        second = p.clone(cloned)
        p.save(second)
        self.assertEqual(p.attribute("bento_kick_v1_tune"), 160)
        self.assertEqual(p.attribute("bento_syncussion_attack"), 28)
        p.save()
        self.assertEqual(p.attribute("bento_kick_v1_tune"), 90)
        self.assertEqual(p.attribute("bento_syncussion_attack"), 75)

    def test_native_clone_can_be_opened_without_resetting_parameters(self):
        p = NativeXml()
        p.edit(KEYS[0], 160)
        p.edit(KEYS[7], 28)
        cloned = p.clone()
        handle = p.r(cloned + 0x10)
        p.types[handle] = 1
        p.w(VIEW + 0x87bc, handle)
        p.call(p.symbol("kick_ui_before"), VIEW)
        self.assertEqual(p.base(KEYS[0]), 160)
        self.assertEqual(p.base(KEYS[7]), 28)

    def test_many_snapshot_copies_do_not_evict_live_sound_and_are_released(self):
        p = NativeXml()
        p.edit(KEYS[0], 160)
        before = bytes(p.u.mem_read(0x24043520, 0x800))
        clones = [p.clone() for _ in range(130)]
        after = bytes(p.u.mem_read(0x24043520, 0x800))
        # The live sound keeps its slot; copies mirror into free slots only.
        self.assertEqual(after[:16], before[:16])
        mirrors = [after[i:i + 16] for i in range(16, 0x800, 16)]
        self.assertEqual(len(mirrors), 127)
        for mirror in mirrors:
            self.assertEqual(mirror[8], 160)
        self.assertEqual(len({struct.unpack_from("<I", m, 4)[0] for m in mirrors}), 127)
        p.save(clones[0])
        self.assertEqual(p.attribute("bento_kick_v1_tune"), 160)
        released = []
        pool = p.u.hook_add(UC_HOOK_CODE, lambda *args: p.ret(),
                            begin=0x08101e9c, end=0x08101e9c)
        free = p.u.hook_add(UC_HOOK_CODE,
                            lambda u, *args: (released.append(u.reg_read(UC_ARM_REG_R0)), p.ret()),
                            begin=0x08104cc4, end=0x08104cc4)
        try:
            for cloned in reversed(clones):
                p.call(0x0812d978, cloned, 0xc0190000)
        finally:
            p.u.hook_del(pool)
            p.u.hook_del(free)
        self.assertEqual(len(released), 130)
        self.assertEqual(p.r(0x2404350c), 0)
        final = bytes(p.u.mem_read(0x24043520, 0x800))
        self.assertEqual(final[:16], before[:16])
        for i in range(16, 0x800, 16):
            self.assertEqual(struct.unpack_from("<I", final, i)[0], 0)

    def test_corrupt_copy_list_is_ignored_and_cut(self):
        p = NativeXml()
        p.edit(KEYS[0], 160)
        cloned = p.clone()
        head = p.r(0x2404350c)
        # A node without the native allocator header or magic ends the list.
        p.w(head, 0xc0180040)
        p.save(cloned)
        self.assertIsNotNone(p.attribute("bento_drum_model"))
        p.save()
        self.assertEqual(p.attribute("bento_kick_v1_tune"), 160)

    def test_native_save_wrapper_preserves_live_settings_and_writes_real_xml(self):
        p = NativeXml()
        for key, value in zip(KEYS, (160, 82, 73, 64, 55, 46, 37, 28)):
            p.edit(key, value)
        p.u.mem_write(0x24043d80, b"\x66")
        before = bytes(p.u.mem_read(0x24043500, 0x900))
        for _ in range(2):
            p.save()
            self.assertEqual(bytes(p.u.mem_read(0x24043500, 0x900)), before)
            self.assertEqual(p.attribute("bento_drum_model"), 15)
            self.assertEqual(p.attribute("bento_kick_v1_tune"), 160)
            self.assertEqual(p.attribute("bento_syncussion_attack"), 28)
            self.assertEqual(p.attribute("bento_drum_v2_click"), 102)

    def test_native_xml_load_restores_all_settings_after_clearing_runtime_cache(self):
        p = NativeXml()
        values = (160, 82, 73, 64, 55, 46, 37, 28)
        for key, value in zip(KEYS, values):
            p.edit(key, value)
        p.u.mem_write(0x24043d80, b"\x66")
        p.save()
        p.u.mem_write(0x24043500, bytes(0x900))
        p.load()
        self.assertEqual(tuple(p.base(key) for key in KEYS), values)
        self.assertEqual(p.u.mem_read(0x24043d80, 1), b"\x66")
        p.save()
        self.assertEqual(p.attribute("bento_syncussion_attack"), 28)


if __name__ == "__main__":
    unittest.main(verbosity=2)
