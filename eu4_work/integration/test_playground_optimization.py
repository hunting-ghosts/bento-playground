"""Pixel and cache regressions for the Playground redraw optimizations."""
import struct
import unittest
import random
from unicorn import UC_HOOK_CODE
from test_tracks import Tracks, POINT, render

TICK = 0x30035f40
TEXT = POINT + 0x100
RECT = POINT + 0x180
GROUND = 480
SHARED_LABEL = 344
POINTS = [
    (-71, 71), (-79, 61), (-87, 50), (-92, 38), (-97, 26), (-99, 13),
    (-100, 0), (-99, -13), (-97, -26), (-92, -38), (-87, -50),
    (-79, -61), (-71, -71), (-61, -79), (-50, -87), (-38, -92),
    (-26, -97), (-13, -99), (0, -100), (13, -99), (26, -97),
    (38, -92), (50, -87), (61, -79), (71, -71), (79, -61),
    (87, -50), (92, -38), (97, -26), (99, -13), (100, 0),
    (99, 13), (97, 26), (92, 38), (87, 50), (79, 61), (71, 71),
]


def cdiv(value, divisor):
    return value // divisor if value >= 0 else -((-value) // divisor)


def reference_ring(cx, cy, radius, start, end):
    pixels = set()
    if start < 0 or end < 0:
        return pixels
    start, end = sorted((start, end))

    def point(at):
        i, fraction = divmod(at, 10)
        j = min(i + 1, 36)
        return tuple(cdiv((POINTS[i][axis] * 10 +
                           (POINTS[j][axis] - POINTS[i][axis]) * fraction) *
                          radius, 1000) + (cx, cy)[axis]
                     for axis in (0, 1))

    while start < end:
        next_angle = min((start // 10 + 1) * 10, end)
        x, y = point(start)
        endx, endy = point(next_angle)
        dx, dy = abs(endx - x), abs(endy - y)
        sx, sy = (-1 if endx < x else 1), (-1 if endy < y else 1)
        err = dx - dy
        while True:
            pixels.update((x + xx, y + yy) for xx in range(2) for yy in range(2))
            if (x, y) == (endx, endy):
                break
            doubled = 2 * err
            if doubled > -dy:
                err -= dy
                x += sx
            if doubled < dx:
                err += dx
                y += sy
        start = next_angle
    return pixels



def pk(a, b):
    """playground_ui.c PK(): two signed 16-bit halves in one argument word."""
    return (a & 0xFFFF) | ((b & 0xFFFF) << 16)


def style(colour, font, align):
    """playground_ui.c STYLE(): colour | font << 8 | align << 16 (low bytes)."""
    return (colour & 0xFF) | ((font & 0xFF) << 8) | ((align & 0xFF) << 16)


def tspec(width, height, colour, font, align):
    """playground_ui.c TSPEC() (run 13): w 12 bits | h 7 | colour 8 | font 3 | align 2 in one argument word."""
    return ((width & 4095) | ((height & 127) << 12) | ((colour & 0xFF) << 19)
            | ((font & 7) << 27) | ((align & 3) << 30))

class PlaygroundOptimizationTests(unittest.TestCase):
    def state(self):
        p = Tracks()
        p.w(TICK, 100)
        p.direct("pg_column_down", 1, 230)
        state = p.e.r(p.call("playground_existing_slot"))
        self.assertNotEqual(state, 0)
        return p, state

    def cached(self, p, state, text, colour=0xf2, ground=0xf1,
               font=0, align=2, width=149, height=28):
        p.w(state + GROUND, ground)
        p.u.mem_write(TEXT, text.encode("ascii") + b"\0")
        # packed ABI (space work): PK(x,top), TSPEC(w,h,colour,font,align) (run 13), text
        p.call("text_cached_", state, render.CTX, 55, pk(40, 100),
               tspec(width, height, colour, font, align), TEXT)

    def reference(self, p, state, text, colour=0xf2, ground=0xf1,
                  font=0, align=2, width=149, height=28):
        p.w(state + GROUND, ground)
        p.u.mem_write(TEXT, text.encode("ascii") + b"\0")
        p.u.mem_write(state + SHARED_LABEL + 0x5c, b"\x01")
        p.call("textf_", state, render.CTX, pk(40, 100),
               tspec(width, height, colour, font, align), TEXT)

    def test_ring_runs_cover_exactly_the_original_stamps(self):
        p = Tracks()
        for cy in (78, 82):
            for radius in (1, 17, 25, 37):
                for start, end in ((0, 360), (3, 87), (250, 75), (359, 360),
                                   (123, 123), (-1, 180)):
                    p.fills.clear()
                    p.call("ring", render.SURF, 200, cy, radius, start, end, 0xf2)
                    actual = set()
                    for (x, bottom, width, height), colour in p.fills:
                        self.assertEqual(colour, 0xf2)
                        top = 480 - bottom - height
                        actual.update((xx, yy) for xx in range(x, x + width)
                                      for yy in range(top, top + height))
                    self.assertEqual(actual, reference_ring(200, cy, radius, start, end),
                                     (cy, radius, start, end))

    def test_track_icon_runs_cover_exactly_the_bitmap(self):
        p = Tracks()
        p.w(TICK, 100)
        p.u.mem_write(render.CTX, struct.pack("<II", 1, render.SURF))
        colour = p.call(0x08140ebc, 0)
        rng = random.Random(731)
        patterns = [(1, 1, lambda x, y: True),
                    (16, 20, lambda x, y: x % 3 == 0),
                    (16, 20, lambda x, y: y % 3 == 0),
                    (64, 64, lambda x, y: (x + y) % 2 == 0),
                    (37, 29, lambda x, y: rng.randrange(3) == 0)]
        for index, (width, height, selected) in enumerate(patterns):
            bitmap = bytes(0x80 if selected(x, y) else 0
                           for y in range(height) for x in range(width))
            address = 0xc3008000 + index * 0x2000
            p.u.mem_write(address, bitmap)
            p.w(p.col(0) + 0x4b4, address)
            p.u.mem_write(p.col(0) + 0x4b8, struct.pack("<HH", width, height))
            p.fills.clear()
            p.call("pg_column_paint", p.col(0), render.CTX)
            actual = set()
            rectangles = []
            for (x, bottom, w, h), fill_colour in p.fills:
                top = 480 - bottom - h
                if (fill_colour == colour and x >= 68 and x + w <= 68 + width
                        and top >= 197 and top + h <= 197 + height):
                    rectangles.append((x, top, w, h))
                    actual.update((xx - 68, yy - 197)
                                  for xx in range(x, x + w)
                                  for yy in range(top, top + h))
            expected = {(x, y) for y in range(height) for x in range(width)
                        if bitmap[y * width + x] & 0x80}
            horizontal = sum((x, y) in expected and (x == 0 or (x - 1, y) not in expected)
                             for y in range(height) for x in range(width))
            vertical = sum((x, y) in expected and (y == 0 or (x, y - 1) not in expected)
                           for y in range(height) for x in range(width))
            self.assertEqual(actual, expected, (width, height))
            self.assertEqual(len(rectangles), min(horizontal, vertical), (width, height))

    def test_cached_labels_match_fresh_native_render_and_invalidate(self):
        p, state = self.state()
        cases = [
            ("Filter", 0xf2, 0xf1, 0, 2, 149, 28),
            ("Filter", 0xf2, 0xf1, 0, 2, 149, 28),
            ("Resonance", 0xf2, 0xf1, 0, 2, 149, 28),
            ("Resonance", 0xf7, 0xf1, 0, 2, 149, 28),
            ("Resonance", 0xf7, 0xf4, 0, 2, 149, 28),
            ("Resonance", 0xf7, 0xf4, 3, 2, 149, 28),
            ("Resonance", 0xf7, 0xf4, 3, 1, 149, 28),
            ("Resonance", 0xf7, 0xf4, 3, 1, 54, 28),
            ("Resonance", 0xf7, 0xf4, 3, 1, 54, 20),
        ]
        for i, args in enumerate(cases):
            render.clear(p.e)
            self.reference(p, state, *args)
            expected = bytes(p.u.mem_read(render.FB, 480 * 1280))
            render.clear(p.e)
            rasterizations = []
            hook = p.u.hook_add(UC_HOOK_CODE, lambda *unused: rasterizations.append(1),
                                begin=0x0817e52a, end=0x0817e52a)
            self.cached(p, state, *args)
            p.u.hook_del(hook)
            self.assertEqual(bytes(p.u.mem_read(render.FB, 480 * 1280)), expected, args)
            self.assertEqual(len(rasterizations), 0 if i == 1 else 1, args)

    def test_evicted_native_label_is_rebuilt_with_the_same_pixels(self):
        p, state = self.state()
        self.cached(p, state, "Return after page switch")
        p.u.mem_write(TEXT, b"Other screen\0")
        p.u.mem_write(RECT, struct.pack("<4I", 40, 352, 149, 28))
        for i in range(130):
            label = 0xc3000000 + i * 128
            p.w(TICK, 101 + i)
            p.call(0x0817e7c0, label)
            p.call(0x0817e810, label, 0)
            p.u.mem_write(label + 0x53, bytes((0xf2, 0xf1, 0, 1)))
            for offset, value in ((4, 40), (8, 352), (12, 149), (16, 28)):
                p.w(label + offset, value)
            p.call(0x0817e85e, label, TEXT)
            p.call(0x0817e448, label, render.CTX, RECT)
        render.clear(p.e)
        self.reference(p, state, "Return after page switch")
        expected = bytes(p.u.mem_read(render.FB, 480 * 1280))
        render.clear(p.e)
        rasterizations = []
        hook = p.u.hook_add(UC_HOOK_CODE, lambda *unused: rasterizations.append(1),
                            begin=0x0817e52a, end=0x0817e52a)
        self.cached(p, state, "Return after page switch")
        p.u.hook_del(hook)
        self.assertEqual(bytes(p.u.mem_read(render.FB, 480 * 1280)), expected)
        self.assertEqual(len(rasterizations), 1)

    def test_cache_allocation_failure_logs_once_and_uses_original_renderer(self):
        p, state = self.state()
        cursor = p.e.r(0x3000004c)
        p.w(0x30000048, cursor + 32)
        render.clear(p.e)
        self.reference(p, state, "No spare memory")
        expected = bytes(p.u.mem_read(render.FB, 480 * 1280))
        render.clear(p.e)
        self.cached(p, state, "No spare memory")
        self.assertEqual(bytes(p.u.mem_read(render.FB, 480 * 1280)), expected)
        self.cached(p, state, "No spare memory")
        self.assertEqual(p.e.r(p.call("playground_label_slot")), 1)
        self.assertEqual(p.diagnostics, ["Playground text cache: no memory"])

    def test_zero_native_cache_clock_uses_shared_renderer(self):
        p, state = self.state()
        p.w(TICK, 0)
        render.clear(p.e)
        self.reference(p, state, "Clock not started")
        expected = bytes(p.u.mem_read(render.FB, 480 * 1280))
        render.clear(p.e)
        self.cached(p, state, "Clock not started")
        self.assertEqual(bytes(p.u.mem_read(render.FB, 480 * 1280)), expected)
        self.assertEqual(p.e.r(p.call("playground_label_slot")), 0)
        p.w(TICK, 100)
        self.cached(p, state, "Clock not started")
        self.assertNotEqual(p.e.r(p.call("playground_label_slot")), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
