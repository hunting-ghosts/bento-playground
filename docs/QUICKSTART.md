# Alpha 1.0: installation and restore

You'll need your own original **Bento 1.6.1** download, with both
`bento1.bin` and `bento2.bin`. Older modified files won't work.

1. Download `Bento_Alpha_1.0_Offline_Patcher.zip` from the
   [Alpha 1.0 release](https://github.com/t4kbsv99sn-source/bento-playground/releases/tag/alpha-1.0).
2. Extract it and open `OPEN_BENTO_PATCHER.html` in a current browser.
3. Choose both original files and click **Create firmware ZIP**.
4. Open the new ZIP and read `00_START_HERE.txt`. Back up your projects
   before following Bento's normal SD-card update procedure.
5. Check that the device shows **Alpha 1.0**. Start with a spare project.

The patcher works offline. Your files stay on your computer, and the originals
stay unchanged. The generated ZIP includes the patched application, unchanged
controller, synth selector WAVs and your stock pair in `03_STOCK_RESTORE`.
Keep that restore folder somewhere safe.

To go back, use **both** original files from the restore folder with the same
normal update procedure. No bootloader is included or changed. The patcher
doesn't connect to the device or install anything for you.

If you prefer the command line, the extracted patcher also works with Python 3:

```sh
python3 patch_bento.py --main /path/to/original/bento1.bin \
  --controller /path/to/original/bento2.bin --out Bento_Alpha_1.0_Install.zip
```

Don't share the generated install ZIP: it contains manufacturer firmware.
Share the patcher release instead. Source-build instructions are in the
[developer guide](DEVELOPER_GUIDE.md).
