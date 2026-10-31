# Building and checking Alpha 1.0

Most of Bento stays stock. These sources patch one exact 1.6.1 application
and add code for the extra instruments, sequencing and UI. The controller
stays unchanged; there is no bootloader patch or automatic flashing.

The folder names come from development and are kept because the build uses
them. They aren't a menu of firmware versions.

| Folder | What's there |
|---|---|
| `eu4_work/integration` | Current sequencer, UI, macros, Motion and audio adapters |
| `eu4_work/drums`, `eu4_work/track_fx` | Instruments and track processors |
| `k16_work`, `k16_overlay`, `tf2_work` | Sources still used by the build underneath |
| `chord_work` | Chord/progression code and checks |
| `patcher`, `tools` | Offline patcher, builders, tests and export helpers |

## Build current source

Use Python 3.10+ and a C++ compiler. The ARM compiler is the pinned Zig Python
package. We use a virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python tools/build_g3.py --stock /path/to/original/bento1.bin --out build/alpha-10
```

The builder checks the input hash, patch bounds, word alignment and exact
reversal. An unchanged-source build should match the application hash in
[STATUS.md](STATUS.md). Generated firmware and restore files stay out of Git.

To prepare the offline patcher from that image and your original pair:

```sh
python tools/package_patcher.py --stock-dir /path/to/original \
  --image build/alpha-10/bento1.bin --out build/alpha-10-patcher \
  --source-url https://github.com/hunting-ghosts/bento-playground/tree/alpha_1.0
python tools/test_patcher.py --patcher build/alpha-10-patcher \
  --stock-dir /path/to/original --image build/alpha-10/bento1.bin
```

The browser-JavaScript check needs Node.js on PATH; the patcher itself needs
no Node installation. On macOS, some Keystone installs need their bundled
library configured before the ARM builders can load it.

For the full firmware checks, first build the unchanged chord test core:

```sh
python chord_work/build.py --out build/chord-core
python tools/validate_p30.py --build build/alpha-10 \
  --stock /path/to/original/bento1.bin --core build/chord-core
```

The full check currently includes a known DSP numerical failure; see
[release status](STATUS.md) for the validation results and hardware limitations.

The release builder pins the functional image before applying the native
release identity (**Alpha 1.0** on the device). It intentionally rejects a different functional image:
changing DSP/UI code requires a new reviewed image/hash rather than silently
packaging changed code as the same release.

Please keep changes small, preserve the native behaviour around them, and
include a test or a clear way to check a fix. Third-party license texts and
provenance stay with their sources. See [publishing notes](PUBLISHING.md)
before putting any generated output online.
