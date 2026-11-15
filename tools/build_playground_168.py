"""Build Bento Playground for official 1.6.8 from your own original firmware files.

  python tools/build_playground_168.py --stock-161 /path/1.6.1/bento1.bin \
      --stock-168 /path/1.6.8 --label "Playground 1.0" --out build/playground-10 [--expect-sha SHA256]

The port is generated, not hand-maintained: Playground's source is written against 1.6.1. This tool
  1. builds the 1.6.1 image (tools/build_g3.py) to learn where every patch and native call sits,
  2. matches those native addresses in your 1.6.8 file (tools/port: inventory, match_report,
     offsets_check, keys, make_profile; the analysis stays in OUT/analysis and is never committed:
     it contains excerpts of the original firmware),
  3. writes a translated copy of the committed source (tools/port/make_tree.py with
     bento_mods/profiles/bento-1.6.8.overrides.json and the reviewed version patch),
  4. builds that copy on your 1.6.8 file (build_g3 of the translated tree).
Both original inputs are hash-checked; nothing is flashed or uploaded; the controller (bento2.bin) is
never patched. The result is OUT/bento1.bin plus its FULL_MANIFEST.json (every write, reversible).
The working tree must be committed: the translation copies `git archive HEAD`.
"""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "tools/port"
STOCK_161 = "14475e9d5068f5659d0fe0b00fc1278c1479c43ed9fda3d40654d5f3a7a6bbb3"   # official 1.6.1 bento1.bin
STOCK_168 = "cb8f830ec3ab45a92d120ae9688e380573b24ad88710a3ad3d21af6ffb3c8d0d"   # official 1.6.8 bento1.bin
CONTROLLER = "8100906327093463fb58f531ee28583423a9881ea3a7d5b77874a7700735e99d"  # bento2.bin (1.6.1 = 1.6.8)
LABEL_161 = "R6.18-s"   # label of the intermediate 1.6.1 build; only its addresses are used


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(cmd, cwd=ROOT, log=None):
    env = dict(os.environ, BENTO_M4_MPU_WIDE="1")
    print("+", " ".join(str(c) for c in cmd), flush=True)
    with (open(log, "w") if log else open(os.devnull, "w")) as f:
        r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env,
                           stdout=f if log else None, stderr=subprocess.STDOUT if log else None)
    if r.returncode:
        raise SystemExit("Step failed (%s)%s" % (cmd[1] if len(cmd) > 1 else cmd[0],
                                                 ", see " + str(log) if log else ""))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--stock-161", type=Path, required=True, help="original 1.6.1 bento1.bin")
    p.add_argument("--stock-168", type=Path, required=True, help="folder with original 1.6.8 bento1.bin and bento2.bin")
    p.add_argument("--label", required=True, help='firmware name shown on the device, e.g. "Playground 1.0"')
    p.add_argument("--out", type=Path, required=True, help="empty output folder")
    p.add_argument("--expect-sha", help="refuse a result with another application SHA-256")
    a = p.parse_args()
    s161, s168, ctl = a.stock_161.resolve(), (a.stock_168 / "bento1.bin").resolve(), (a.stock_168 / "bento2.bin").resolve()
    if sha(s161) != STOCK_161:
        raise SystemExit("--stock-161 is not the original 1.6.1 bento1.bin")
    if sha(s168) != STOCK_168:
        raise SystemExit("--stock-168/bento1.bin is not the original 1.6.8 file")
    if sha(ctl) != CONTROLLER:
        raise SystemExit("--stock-168/bento2.bin is not the original controller file")
    if subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                      capture_output=True, text=True).stdout.strip():
        raise SystemExit("Commit your changes first: the 1.6.8 tree is translated from `git archive HEAD`")
    out = a.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit("Choose an empty output folder")
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    work.mkdir()
    b161, ana, tree, b168 = work / "build-1.6.1", work / "analysis", work / "tree-1.6.8", work / "build-1.6.8"
    ana.mkdir()
    py = sys.executable
    run([py, ROOT / "tools/build_g3.py", "--stock", s161, "--out", b161, "--syncussion", "--no-motion",
         "--candidate-label", LABEL_161], log=work / "build-1.6.1.log")
    run([py, PORT / "inventory.py", "--build", b161, "--stock", s161, "--root", ROOT, "--out", ana / "inventory.json"])
    run([py, PORT / "match_report.py", "--inventory", ana / "inventory.json", "--old", s161, "--new", s168,
         "--out", ana / "match.json"], log=work / "match.log")
    run([py, PORT / "offsets_check.py", "--inventory", ana / "inventory.json", "--old", s161, "--new", s168,
         "--out", ana / "constants.json"], log=work / "offsets.log")
    run([py, PORT / "keys.py", "--old", s161, "--new", s168, "--out", ana / "keys.json"], log=work / "keys.log")
    run([py, PORT / "make_profile.py", "--inventory", ana / "inventory.json", "--match", ana / "match.json",
         "--offsets", ana / "constants.json", "--keymap", ana / "keys.json", "--old", s161, "--new", s168,
         "--controller", ctl, "--out", ana / "profile.draft.json"], log=work / "profile.log")
    run([py, PORT / "make_tree.py", "--profile", ana / "profile.draft.json",
         "--overrides", ROOT / "bento_mods/profiles/bento-1.6.8.overrides.json",
         "--patch", ROOT / "bento_mods/profiles/bento-1.6.8.patch", "--out", tree, "--experimental"],
        log=work / "tree.log")
    run([py, tree / "tools/build_g3.py", "--stock", s168, "--out", b168, "--syncussion", "--no-motion",
         "--candidate-label", a.label], cwd=tree, log=work / "build-1.6.8.log")
    image = (b168 / "bento1.bin").read_bytes()
    manifest = json.loads((b168 / "FULL_MANIFEST.json").read_text())
    digest = hashlib.sha256(image).hexdigest()
    assert manifest["sha256"] == digest and manifest["stock_sha256"] == STOCK_168, "manifest mismatch"
    assert manifest["label"] == a.label, "label mismatch"
    assert len(image) % 4 == 0 and 0x08040000 + len(image) <= 0x081E0000, "alignment / application bound"
    if a.expect_sha and digest != a.expect_sha.lower():
        raise SystemExit("Built %s, expected %s: refusing to call this the same release" % (digest, a.expect_sha))
    shutil.copy(b168 / "bento1.bin", out / "bento1.bin")
    shutil.copy(b168 / "FULL_MANIFEST.json", out / "FULL_MANIFEST.json")
    print(a.label, digest, len(image), "bytes ->", out / "bento1.bin")
    print("Translated tree (run its tests from there):", tree)


if __name__ == "__main__":
    main()
