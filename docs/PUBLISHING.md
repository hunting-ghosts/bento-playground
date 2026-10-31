# Sharing Playground

Share source and the offline patcher, not manufacturer firmware. The patcher
uses each person's own original files and builds their install ZIP locally.
That generated ZIP includes firmware and restore files and isn't a release
asset to redistribute.

Release snapshots contain current source and guides, not development archives
or old tester packages. Build source is copied unchanged; user-facing docs
live separately.
The release manifest records source hashes and the exact application hash.

Before sharing another release, reproduce the image from the exported source,
check both patcher paths, preserve the licenses, and review the outgoing files
for firmware, personal data and private notes. Software checks and hardware
results need to stay separate. Don't change repository visibility without
the maintainer asking for it.

Our additions are GPL-3.0-or-later. DaisySP retains its MIT/LGPL-2.1 notices
and provenance. None of that grants rights to redistribute 1010music's code.
