"""R6.15: Kick retrigger through the real native sampler path (test harness).

Router queue (real 08065600 post) -> sampler block process 0808E9A0(root, router):
event 0x12 (sequencer note) -> 08094760 key note-on, or 0x4E (pad) -> 08093BA0;
native voice allocation over root+0x20 (count root+0x60, mode root+0xF4), our
kick_voice hooks inside those paths, native render loop (0808FC80: 08091820 ->
kick_render -> native postprocess 08092D00 into router output 0) and 08093780.
Fixtures: the sample lookup 080872C0 (copies the pad's sample into the voice's
own descriptor object voice+0x10), the sample provider's status/channel calls,
the transport clock object, the engine's voice-age counter object."""
import struct, sys, collections
from engine_test_support import engine, SYMS
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_PC

R, Q, EVT, CLOCK, ENGINE = 0x20030000, 0x20031000, 0x20032000, 0x20036000, 0x20033000
BUF = 0x20037000
VOICE_CTOR, VOICE_ATTACH, RAMP_RELEASE = 0x08072a00, 0x08092f20, 0x08063960  # native: voice constructor, attach to a sampler root, ramp release
RANDOM, SEED = 0x24042004, 0x2545f491
N = 64


def obj(p, at, n, left, right=None, stereo=True):
    p.u.mem_write(at, bytes(20))
    p.w(at, n); p.w(at + 4, n); p.w(at + 8, left); p.w(at + 12, right or left + 0x400)
    p.u.mem_write(at + 0x11, b"\1" if stereo else b"\0")


class Native:
    def __init__(self, values, voices=4, mode=4, armed=True, preload=True):
        p = self.p = engine(1, values)
        p.native_postprocess()
        self.voices = [p.voice] + [0x20018000 + 0x800 * i for i in range(1, voices)]
        for v in self.voices[1:]:
            p.u.mem_write(v, bytes(0x800)); p.call(VOICE_CTOR, v); p.call(VOICE_ATTACH, p.root, v)
        # The fixture's first voice: own embedded descriptor object like the rest.
        p.u.mem_write(p.voice + 0x10, bytes(p.u.mem_read(p.desc, 0x2c))); p.w(p.voice + 12, p.voice + 0x10)
        self.sample = bytes(p.u.mem_read(p.desc, 0x2c))
        for v in self.voices[1:]:
            # preload: every voice has played this pad before (steady state);
            # otherwise its descriptor object is still empty at first use.
            p.u.mem_write(v + 0x10, self.sample if preload else bytes(0x2c)); p.w(v + 12, v + 0x10)
        if armed:  # the native loader arms a Drum Synth pad (kick_enable)
            p.call(SYMS['kick_enable'], p.root, 1)
        for i, v in enumerate(self.voices):
            p.w(p.root + 0x20 + 4 * i, v); p.u.mem_write(v, b"\0")
        p.w(p.root + 0x60, len(self.voices))
        p.u.mem_write(p.root + 0x1d, b"\1"); p.w(p.root + 0xf4, mode)
        p.w(p.root + 0x18, ENGINE); p.u.mem_write(ENGINE + 0xc700, bytes(16))
        vt = p.r(p.provider); p.w(vt + 0x18, 0x081be031); p.w(vt + 0x24, 0x081be041)
        p.u.hook_add(UC_HOOK_CODE, self._provider, begin=0x081be030, end=0x081be030)
        p.u.hook_add(UC_HOOK_CODE, self._provider, begin=0x081be040, end=0x081be040)
        p.u.hook_add(UC_HOOK_CODE, self._lookup, begin=0x080872c0, end=0x080872c0)
        p.u.mem_write(R, bytes(0x1000)); p.u.mem_write(Q, bytes(0x700)); p.u.mem_write(CLOCK, bytes(0x400))
        p.f(CLOCK + 0x18, 120); p.f(CLOCK + 0x14c, .5); p.w(R, CLOCK)
        p.w(R + 0x508, 1); p.w(R + 8, 101); p.w(R + 12, 0); p.w(R + 4, Q)
        k = struct.unpack("<H", p.u.mem_read(p.root + 0x670, 2))[0]
        obj(p, R + 0x5ac + 20 * k, N, BUF)                 # track output: the native postprocess mixes every voice here
        obj(p, R + 0x764, N, BUF + 0x1000)                 # loop scratch (0809EE00 index 0)
        obj(p, R + 0x764 + 40, 128, BUF + 0x2000, BUF + 0x3000)  # per-voice buffer
        obj(p, R + 0xe1c, 128, BUF + 0x4000, BUF + 0x5000)  # temp
        self.log = []
        for a, n in ((SYMS['kick_voice'], 'kick_voice'), (0x08094760, 'key_on'), (0x08093ba0, 'pad_on'),
                     (0x08091820, 'render')):
            p.u.hook_add(UC_HOOK_CODE, lambda u, a, s, d, n=n: self.log.append(
                (n, u.reg_read(UC_ARM_REG_R0), u.reg_read(UC_ARM_REG_R1))), begin=a, end=a)
        for v in self.voices:
            p.u.hook_add(UC_HOOK_MEM_WRITE, lambda u, acc, a, sz, val, d, v=v: self.log.append(
                ('active', v, val & 255, u.reg_read(UC_ARM_REG_PC))), begin=v, end=v)

    def _provider(self, u, a, s, d):
        if a == 0x081be030:
            self.p.w(u.reg_read(UC_ARM_REG_R0) + 4, 0); self.p.ret(0)
        else:
            self.p.ret(1)

    def _lookup(self, u, a, s, d):
        u.mem_write(u.reg_read(UC_ARM_REG_R2), self.sample[:0x28]); self.p.ret(1)

    def post(self, kind, frame=0, note=60, velocity=1.0):
        p = self.p
        if kind == 0x12:
            ev = struct.pack("<B3xIIIf4x", 0x12, frame, 101, note, velocity)
        else:
            ev = struct.pack("<B3xIIIi4x", kind, frame, 101, note, int(velocity * 127))
        p.u.mem_write(EVT, ev); p.call(0x08065600, Q, EVT)

    def block(self):
        p = self.p
        p.u.mem_write(BUF, bytes(0x800))
        self.log.clear()
        from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_R0 as R0, UC_ARM_REG_R1 as R1
        p.u.reg_write(R0, p.root); p.u.reg_write(R1, R)
        p.u.reg_write(UC_ARM_REG_SP, 0x2003f000); p.u.reg_write(UC_ARM_REG_LR, p.stop | 1)
        p.u.emu_start(0x0808e9a0 | 1, 0, count=3000000)  # several voices exceed the fixture's 100k cap
        assert p.u.reg_read(UC_ARM_REG_PC) == p.stop
        p.w(Q + 0x600, 0)
        return list(struct.unpack("<64f", p.u.mem_read(BUF, 256)))

    def active(self):
        return [self.p.u.mem_read(v, 1)[0] for v in self.voices]


def run(values, k=None, blocks=40, kind=0x12, first=True, voices=4, mode=4, trace=None, armed=True, preload=True, frame=0):
    """First hit at block 0 (unless first=False), retrigger at block k (event frame offset)."""
    n = Native(values, voices, mode, armed, preload); out = []
    for b in range(blocks):
        if b == 0 and first:
            n.post(kind)
        if b == k:
            n.p.w(RANDOM, SEED); n.post(kind, frame)
        out.extend(n.block())
        if trace is not None and b in (0, k):
            trace.append((b, list(n.log), n.active()))
    return out


import math
A = math.exp(-2 * math.pi * 2000 / 48000)


def hf(x, w0, w1, pre=256):
    """Energy above 2 kHz (4-pole one-pole high-pass), as research/click_study/retrigger_hf.py."""
    y = x[max(0, w0 - pre):w1]
    for _ in range(4):
        out = []; px = py = 0.
        for v in y:
            py = A * (py + v - px); px = v; out.append(py)
        y = out
    return sum(v * v for v in y[w0 - max(0, w0 - pre):])


def click(values, k, frame=0, **kw):
    """(actual, ideal): HF energy of what is left of the old voice after the
    retrigger (actual minus the same new hit alone), and of the old voice with
    an ideal 5 ms cosine fade-out from the retrigger."""
    blocks = k + 8
    act = run(values, k, blocks, frame=frame, **kw)
    new = run(values, k, blocks, first=False, frame=frame, **kw)
    old = run(values, None, blocks, **kw)
    t0 = k * 64
    res = [a - b for a, b in zip(act, new)]
    fade = [old[i] if i < t0 else (old[i] * .5 * (1 + math.cos(math.pi * (i - t0) / 240)) if i < t0 + 240 else 0.)
            for i in range(len(act))]
    w0, w1 = t0 - 16, t0 + 448
    return hf(res, w0, w1), hf(fade, w0, w1), hf(old, w0, w1), res, old


# ---------------------------------------------------------------------------
# R6.16: the ratchet chain on the same real sampler path. The M7 player arms a
# note (rt_live, the live scheduler's entry; the native renderer's adapter
# uses the same arm()), the real rt_block plays the later hits through the
# native note-on 0805F8E0 and the real router post 0809F040 into this router,
# and the sampler's voice start runs rt_voice (mono roll) before kick_voice.
from pathlib import Path as _Path


def _symbols(path):
    d = path.read_bytes(); shoff, = struct.unpack_from("<I", d, 0x20); es, n, _ = struct.unpack_from("<HHH", d, 0x2e)
    S = [struct.unpack_from("<10I", d, shoff + i * es) for i in range(n)]; out = {}
    for s in S:
        if s[1] != 2:
            continue
        st = S[s[6]]
        for i in range(0, s[5], 16):
            nm, v, _, info, _, _ = struct.unpack_from("<IIIBBH", d, s[4] + i)
            if info & 15 == 2:
                out[d[st[4] + nm:d.index(b"\0", st[4] + nm)].decode()] = v & ~1
    return out


RT = _symbols(_Path(__file__).resolve().parent / "integration/ratchet_audio.elf")
SDRAM, SEQ, CLIP, RTB, REC = 0xc5000000, 0xc5000000, 0xc5009000, 0xc5010000, 0xc500c000
LC_MAGIC, RT_TAG = 0x37434c42, 0x52000000


def call(p, address, *args):
    """AAPCS call with any number of word arguments (r0-r3, then the stack)."""
    from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_R3
    regs = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]
    sp = 0x2003f000 - 64
    for i, v in enumerate(args):
        if i < 4:
            p.u.reg_write(regs[i], v & 0xffffffff)
        else:
            p.w(sp + 4 * (i - 4), v)
    p.u.reg_write(UC_ARM_REG_SP, sp); p.u.reg_write(UC_ARM_REG_LR, p.stop | 1)
    p.u.emu_start(address | 1, 0, count=3000000)
    assert p.u.reg_read(UC_ARM_REG_PC) == p.stop, hex(p.u.reg_read(UC_ARM_REG_PC))
    return p.u.reg_read(UC_ARM_REG_R0)


class Chain(Native):
    def __init__(self, values, voices=4, mode=4, sample=False, grid=10, **kw):
        super().__init__(values, voices, mode, armed=not sample, **kw)
        p = self.p
        if sample:  # an ordinary sample: not a Kick carrier; the native sampler renders it
            sm = bytearray(self.sample); struct.pack_into("<I", sm, 0x24, 48000 * 4); self.sample = bytes(sm)
            p.u.mem_write(p.voice + 0x10, self.sample[:0x28])
        p.u.mem_map(SDRAM, 0x20000)
        s = SEQ; p.u.mem_write(s, bytes(0x9000))
        p.u.mem_write(s + 0x20, b"\1"); p.w(s + 12, 80); p.w(s + 0x10, 101); p.w(s + 0x86c0, CLIP)
        for i in range(16):
            p.w(s + (0x21b6 + i) * 4 + 4, 0xffffff00)
        p.u.mem_write(s + 0x8000 + 0x6d2, b"\1")  # note output on
        p.w(CLIP, grid); p.u.mem_write(CLIP + 0x38, b"\1")  # step clip (10 = 1/16, 14 = 1/64)
        p.u.mem_write(RTB, bytes(0x2000)); p.w(RTB, 0x31425452)
        for i in range(8):
            p.u.mem_write(RTB + 40 + i, b"\x64")
        p.w(0x24041fdc, RTB)
        self.position = 0

    def token(self, count, shape=0, depth=0, prob=0):
        """An immutable EU7 ratchet-only record (as the M4 writes it)."""
        r = RT_TAG | (count - 1) | shape << 3 | depth << 8 | prob << 16; a = REC; p = self.p
        c12 = LC_MAGIC ^ a ^ 0 ^ 0
        p.u.mem_write(a, struct.pack("<8I", LC_MAGIC, 0, 0, c12, r, ~(c12 ^ r) & 0xffffffff, 0, 0))
        return 0x60000000 | (a & 0x0fffffff)

    def note(self, token, vel=100, frame=0):
        """A note as the live scheduler plays it: arm, then the native note-on."""
        p = self.p
        p.w(CLOCK, self.position); p.w(CLOCK + 4, 0)
        first = call(p, RT['rt_live'], SEQ, token, 0, vel, frame, CLOCK, 960, 0)
        call(p, 0x0805f8e0, SEQ, 0, first, frame, 0, R)
        return first

    def run_block(self):
        p = self.p
        p.w(CLOCK, self.position); p.w(CLOCK + 4, 0)
        call(p, RT['rt_block'], SEQ, CLOCK, 0, N, R)
        out = self.block(); self.position += N
        return out
