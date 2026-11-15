# Installation and restore

There's no ready-made download of Bento Playground at the moment. To try the
current state you need to build it yourself from this source and your own
original firmware files, as described in the [developer guide](DEVELOPER_GUIDE.md).
That needs some comfort with the command line.

Back up your projects (copy the whole SD card) before installing anything.

## Install a build

The build gives you a patched `bento1.bin`. Install it together with the
**unchanged** `bento2.bin` from your original 1.6.8 download, using Bento's
normal SD-card update procedure. Never mix files from different versions.
Nothing here connects to the device or installs anything for you, and no
bootloader is included or changed.

Then check the firmware name (below) and start with a spare project.

On its first start, Bento Playground creates a `Drum Synths` folder on the SD card
with small silent marker files. They select the drum synths and the Analog
synth; they aren't samples. Leave them where they are.

The first start after installing new firmware can take a little longer, and
the Bento may **restart once or twice** on its own before it settles. If it
keeps restarting after the third start, go back to the official firmware as
described below and please [report it](https://github.com/hunting-ghosts/bento-playground/issues/new?template=bug_report.md).

## Which firmware is installed

Press **PROJ** until you reach **Settings**. The firmware name is shown there,
for example **P168 exp8b**, or the label you chose for your own build.
Please quote that name in every bug report.

## Back to official 1.6.8

Install **both** original files of your 1.6.8 download (`bento1.bin` and
`bento2.bin`) with the same normal update procedure. Because the bootloader is
never touched, the usual route always works.

Projects saved with Bento Playground should open on official 1.6.8, but this
hasn't been tested in depth. Playground-only settings don't carry over. Notes
using 1ST/!1ST/PRE/!PRE play on every pass there and show a wrong condition
name, as A:B conditions always have. Keep backups of anything important.

Don't share your build: it contains manufacturer firmware.
