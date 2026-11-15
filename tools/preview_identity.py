"""Guarded Alpha 1.0 identity on the exact W22 application; no DSP changes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

BASE = 0x08040000
W22_SHA = "d618b84c271d1f1791597a13d3304bbcc617132b4aad73dbf19c624234240724"
LABEL = "Alpha 1.0"
VERSION = 0x081DFE8C
POINTERS = (0x08131054, 0x08162AD8)
COPY = 0x08162A9A
COPY_BEFORE = bytes.fromhex("93e803000090adf804106946")
COPY_AFTER = bytes.fromhex("194600bf00bf00bf00bf00bf")
ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def apply(image):
    if digest(image) != W22_SHA:
        raise ValueError("Expected the exact delivered W22 application")
    if BASE + len(image) != VERSION:
        raise ValueError("Unexpected W22 application end")
    return _apply_identity(image, LABEL, VERSION)


def apply_candidate(image, label):
    """Identity for freshly compiled, manifest-checked Playground candidates."""
    if not label or not label.isascii() or "\0" in label or len(label) > 31:
        raise ValueError("Candidate identity must be 1-31 printable ASCII characters")
    if any(ord(c) < 32 or ord(c) > 126 for c in label):
        raise ValueError("Candidate identity contains a control character")
    return _apply_identity(image, label, BASE + len(image))


def _apply_identity(image, label, version):
    if len(image) % 4 or version != BASE + len(image):
        raise ValueError("Identity must follow a word-aligned application")
    result = bytearray(image)
    writes = []
    changes = [(a, struct.pack("<I", 0x0818BAD4), struct.pack("<I", version))
               for a in POINTERS]
    text = label.encode() + b"\0"
    text += bytes(-len(text) % 4)
    changes += [(COPY, COPY_BEFORE, COPY_AFTER),
                (version, b"", text)]
    for address, before, after in changes:
        offset = address - BASE
        if result[offset:offset + len(before)] != before:
            raise ValueError("Identity preimage mismatch at " + hex(address))
        result[offset:offset + len(after)] = after
        writes.append(dict(address=address, size=len(after),
                           original_hex=before.hex(), replacement_hex=after.hex(),
                           reason=label + " native version identity"))
    if len(result) % 4 or BASE + len(result) > 0x081E0000:
        raise ValueError("Application identity alignment/bound violation")
    restored = bytearray(result)
    for w in reversed(writes):
        o = w["address"] - BASE
        restored[o:o + w["size"]] = bytes.fromhex(w["original_hex"])
    if bytes(restored) != image:
        raise ValueError("Identity reversal failed")
    return bytes(result), writes


def displayed_version(image):
    for address in POINTERS:
        if struct.unpack_from("<I", image, address - BASE)[0] != VERSION:
            raise ValueError("Native version pointer mismatch")
    if image[COPY - BASE:COPY - BASE + len(COPY_AFTER)] != COPY_AFTER:
        raise ValueError("Native version display adapter mismatch")
    return image[VERSION - BASE:].split(b"\0", 1)[0].decode("ascii")


def reuse(build, out):
    """Reuse a source-matched W22 build instead of recompiling unchanged engines."""
    manifest = json.loads((build / "FULL_MANIFEST.json").read_text())
    inputs = json.loads((build / "SOURCE_INPUTS.json").read_text())
    for name, sha in inputs.items():
        if digest((ROOT / name).read_bytes()) != sha:
            raise ValueError("W22 source input changed: " + name)
    before = (build / "bento1.bin").read_bytes()
    if manifest["sha256"] != digest(before):
        raise ValueError("W22 manifest mismatch")
    image, writes = apply(before)
    for w in writes:
        if any(w["address"] < x["address"] + x["size"] and
               x["address"] < w["address"] + w["size"] for x in manifest["writes"]):
            raise ValueError("Identity overlaps an existing patch")
    shutil.copytree(build, out)
    (out / "bento1.bin").write_bytes(image)
    manifest.update(label=LABEL, sha256=digest(image), identity_base_sha256=W22_SHA)
    manifest["writes"] += writes
    (out / "FULL_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    palette = json.loads((out / "PALETTE_MANIFEST.json").read_text())
    palette["writes"] += writes
    (out / "PALETTE_MANIFEST.json").write_text(json.dumps(palette, indent=2) + "\n")
    (out / "PREVIEW_IDENTITY.json").write_text(json.dumps(dict(
        label=LABEL, before_sha256=W22_SHA, sha256=digest(image),
        bytes=len(image), end=hex(BASE + len(image)), writes=writes,
        tool_sha256=digest(Path(__file__).read_bytes()),
        unchanged_source_inputs=len(inputs),
    ), indent=2) + "\n")
    print(LABEL, digest(image), len(image), "bytes; source-matched W22 identity only")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    reuse(a.build, a.out)
