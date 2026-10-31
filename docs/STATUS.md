# Alpha 1.0: status and limitations

**First alpha.** Tested incrementally by the maintainer on one Bento; broader
hardware testing is still needed. This is not a stable or manufacturer-supported
release.

## Current limits

- Motion supports only the [documented encoders](USER_GUIDE.md#supported-controls).
  There are four clip-length A-D lanes, not an unlimited independent recorder.
- Motion and busy Euclidean patterns can be CPU-intensive. The added features do not remove the device's CPU limits; see the
  [performance tips](USER_GUIDE.md#performance).
- Euclidean Copy/Move/Double/Undo combinations need further work. Double Seq
  has a report of omitting generated notes.
- Full project save/reload and mixed-feature sessions need more device coverage.
  Keep original project backups.
- Track FX gain-reduction telemetry is unfinished.
- Wavetable Position capture, waveform-label restoration, PLAY-held pad lights
  and the full on-device version name require device confirmation.

## Software evidence

Software validation comprises 865 passing functional checks, five skips and
one inherited DSP numerical failure, plus five release-identity checks covering
both native version-string consumers. Browser and Python patcher checks verify
the generated image and stock restores byte-for-byte. The functional results
come from the unchanged baseline; the complete suite was not rerun after the
release-label change.

The DSP failure also occurs with identical baseline DSP source. It is not
counted as a pass and does not by itself establish an audible product defect.
Software checks do not prove device stability, timing, recovery or safety.

Expected Alpha 1.0 application SHA-256:

```text
ca569652cafc82efbc339bdd38ae81a5a8673caff7ce76b67bff18774c74ec4e
```

For feedback, include version/hash, actions, expected/observed behaviour and
reproduction steps. Do not upload firmware images, personal projects or samples.
