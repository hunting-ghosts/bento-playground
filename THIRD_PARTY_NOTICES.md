# Licensing

Bento Playground's own code and documentation are licensed under the
**GNU General Public License v3.0 or later** (see [LICENSE](LICENSE)).

Bundled third-party code keeps its original license. Each copy sits in a
`vendor/` folder next to its license file:

| Component | Where | License |
| --- | --- | --- |
| DaisySP (Electrosmith) — drum voices, oscillator, filter and utility helpers | `*/vendor/daisysp/` | MIT, see the `LICENSE` file in that folder |
| DaisySP-LGPL (Electrosmith) — compressor and biquad | `*/vendor/DaisySP-LGPL/` | LGPL-2.1, see the `LICENSE` file in that folder |
| KnowYourSynth (Sunrise Contributors) — control mappings and six-mode topology adapted in the Metal drum synth (`syncussion*.h`) | `eu4_work/drums/` | MIT, see `eu4_work/drums/syncussion.LICENSE` |

The exact upstream commits and every local change to vendored files are
recorded in the `UPSTREAM.json` file beside each vendor folder; the
KnowYourSynth source commit is named in its license file.

## What this repository does not contain

No 1010music firmware is included, and none should ever be added. The build
tools read *your own* original Bento 1.6.1 and 1.6.8 files and patch them
locally.
Firmware images you build contain 1010music's code as well as ours: keep them
for your own device and do not redistribute them.

Bento is a product and trademark of 1010music. This is an unofficial community
project and is not affiliated with or endorsed by 1010music.
