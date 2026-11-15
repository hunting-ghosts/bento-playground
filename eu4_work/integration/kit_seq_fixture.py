"""M4-only in-memory fixture, never a flashable firmware or replacement manifest.

Reuses a verified source-matched predecessor's native adapters/audio. Redirects
adapter references to newly compiled M4 symbols and loads its checked sections.
Full image construction, hashes/reversal and validation remain release gates.
"""
import os
from pathlib import Path
import struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from capstone.arm import ARM_OP_IMM
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
import build_fx
import kit_seq_input


def current_ui(image, manifest, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    os.environ["BENTO_SYNCUSSION"] = "1"
    chunks, symbols = build_fx.compile_ui(directory / "ui.elf")
    bounds = dict(build_fx.UI_PADS + build_fx.UI_RETIRED + build_fx.UI_BANK1)
    bounds[build_fx.UI] = 0x081E0000 - 24
    for address, data in chunks:
        assert address + ((len(data)+3) & ~3) <= bounds[address], \
            (hex(address), len(data), hex(bounds[address]))
    old = manifest["ui_symbols"]
    target = {value: symbols[name] for name, value in old.items()
              if name in symbols}
    out = bytearray(image)
    out.extend(bytes(max(0, max(a+len(d)-build_fx.BASE for a, d in chunks) - len(out))))
    cs = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    cs.detail = True
    cs.skipdata = True
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    for write in manifest["writes"]:
        address = write["address"]
        if address < 0x08100000 or any(a <= address < a+len(d)
                                      for a, d in chunks):
            continue
        data = bytes.fromhex(write["replacement_hex"])
        if address == build_fx.UI_STUB:
            data = data[:build_fx.UI-build_fx.UI_STUB]
        result = bytearray(data)
        for ins in cs.disasm(data, address):
            if ins.id and ins.mnemonic in ("bl", "b.w") and \
                    len(ins.operands) == 1 and ins.operands[0].type == ARM_OP_IMM:
                old_target = ins.operands[0].imm & ~1
                if old_target in target:
                    replacement = bytes(ks.asm(ins.mnemonic+" "+hex(target[old_target]),
                                               ins.address)[0])
                    assert len(replacement) == ins.size
                    result[ins.address-address:ins.address-address+ins.size] = replacement
        for offset in range(0, len(data)-3, 4):
            value = struct.unpack_from("<I", data, offset)[0]
            if value in target:
                struct.pack_into("<I", result, offset, target[value])
            elif value & 1 and value-1 in target:
                struct.pack_into("<I", result, offset, target[value-1] | 1)
        out[address-build_fx.BASE:address-build_fx.BASE+len(result)] = result
    for address, data in chunks:
        out[address-build_fx.BASE:address-build_fx.BASE+len(data)] = data
    input_base = bytearray(image)
    for write in manifest["writes"]:
        if write["address"] not in (kit_seq_input.START, kit_seq_input.SITE):
            continue
        at = write["address"]-build_fx.BASE
        current = bytes.fromhex(write["replacement_hex"])
        original = bytes.fromhex(write["original_hex"])
        assert input_base[at:at+len(current)] == current
        input_base[at:at+len(original)] = original
    for address, data, expected, _ in kit_seq_input.writes_for(input_base):
        assert input_base[address-build_fx.BASE:address-build_fx.BASE+len(expected)] == expected
        out[address-build_fx.BASE:address-build_fx.BASE+len(data)] = data
    return bytes(out), symbols
