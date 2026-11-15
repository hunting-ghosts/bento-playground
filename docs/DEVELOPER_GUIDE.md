# Building and checking Bento Playground

Most of Bento stays stock. These sources patch one exact application image
and add code for the extra instruments, sequencing and UI. The controller
stays unchanged; there is no bootloader patch or automatic flashing.

Playground's source is written against **1.6.1**. The **1.6.8** build is
generated from it: a tool finds every native address Playground uses in your
own 1.6.8 file and writes a translated copy of the source, which is then
built on 1.6.8. So you need **both** original downloads to build Bento Playground for 1.6.8:
`bento1.bin` from 1.6.1, and `bento1.bin` + `bento2.bin` from 1.6.8.

The folder names come from development and are kept because the build uses
them. They aren't a menu of firmware versions.

| Folder | What's there |
|---|---|
| `eu4_work/integration` | Current sequencer, UI, macros, ratchets, Motion and audio adapters |
| `eu4_work/drums`, `eu4_work/track_fx` | Instruments and track processors |
| `k16_work`, `k16_overlay`, `tf2_work` | Sources still used by the build underneath |
| `chord_work` | Chord/progression code and checks |
| `tools/port`, `bento_mods/profiles` | 1.6.1 → 1.6.8 address matching, translation and the reviewed version patch |
| `research/display_emulator` | Emulator used by the tests (runs the real firmware code) |
| `tools` | Builders, tests and helpers |

## Build for 1.6.8

Use Python 3.10+ and clang as your C/C++ compiler (`cc`). The ARM compiler is
the pinned Zig Python package. We use a virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python tools/build_playground_168.py \
  --stock-161 /path/to/original-1.6.1/bento1.bin \
  --stock-168 /path/to/original-1.6.8 \
  --label "my build" --out build/playground
```

`--stock-168` is the folder with the 1.6.8 `bento1.bin` and `bento2.bin`.
The tool checks all input hashes, builds 1.6.1 first to learn where every
patch sits, matches those places in 1.6.8, translates the committed source
and builds it on 1.6.8. It takes a few minutes. Commit your changes first:
the translation copies `git archive HEAD`, not your working files.

The builder checks patch bounds, word alignment and exact reversal to your
original file (see [Build identity](#build-identity) for reproducing the
published hash). Generated firmware, restore files and the analysis folder
(`build/.../work/analysis`, which contains excerpts of the original firmware)
stay out of Git.

On macOS, some Keystone installs need their bundled library configured
before the ARM builders can load it.

## Checks

The test suites run the real firmware code in an emulator, against the
original firmware as the reference. For 1.6.8, run them **inside the
translated tree** (`build/playground/work/tree-1.6.8`), with the chord engine
built from that tree:

```sh
cd build/playground/work/tree-1.6.8
python chord_work/build.py --out ../chord-core-168
BENTO_M4_MPU_WIDE=1 python tools/validate_p30.py --build ../build-1.6.8 \
  --stock /path/to/original-1.6.8/bento1.bin --core ../chord-core-168
```

Run from the repository instead, or with the 1.6.1 chord engine, they report
false failures. `--only safety,ratchet` runs single suites while you work.

The same source still builds for 1.6.1 (`tools/build_g3.py --stock
/path/to/original-1.6.1/bento1.bin --out build/b161 --syncussion --no-motion
--candidate-label "my test"`, with `BENTO_M4_MPU_WIDE=1`), and every change
should keep both versions green.

### GitHub Actions

The maintainer runs the full build and every suite for both 1.6.1 and 1.6.8
on GitHub Actions for each change, and reads only the text results; no
firmware image leaves the runner. Because the original firmware can't be put
in a public repository, the workflow isn't part of this export. In your own
fork you can do the same with your original files in a **private** location
that the workflow downloads (for example a private repository read with a
token stored as a secret). Never commit them or publish them.

## Porting to another firmware version

Moving to 1.6.8 was done with a method, not by hand: list every place where
Playground touches or calls the original code (the hook inventory), find each
one in the new version from its surrounding instructions (the hook finder),
compare the result with a second matcher, and review the few places where
the two disagree. The method and the tools are written up in the community
lab's
[porting notes](https://github.com/hunting-ghosts/bento-community-lab/tree/main/research/porting).
`tools/port` here holds the versions this source was built with.

## Build identity

`--label` is the name the device shows in Settings. Use your own name for
your builds so bug reports stay clear. Building this source unchanged with
the label `P168 exp8b` reproduces the application hash in
[STATUS.md](STATUS.md); add `--expect-sha <hash>` to make the builder refuse
anything else. Changed DSP/UI code gives a different image and hash.

Please keep changes small, preserve the native behaviour around them, and
include a test or a clear way to check a fix. Third-party license texts and
provenance stay with their sources. See [publishing notes](PUBLISHING.md):
generated firmware never goes online.
