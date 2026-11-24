# keymap-capture

Recovers a QMK keymap from a running keyboard whose flash cannot be read, by recording what
each key sends. Written for the DZ60 (`FEED:2260`); change `VID`/`PID` in `capture.py` and pass
another board's `keyboard.json` for anything else.

Needs macOS Input Monitoring for the terminal that runs it, and `uv`. The DZ60's media and
mouse interfaces are opened exclusively, so a power or sleep key reaches only the script.

```sh
./capture.py --layer 0                              # every key, no layer held
./capture.py --layer 1 --layout LAYOUT_directional  # hold layer 1's key throughout
./capture.py --hold-test                            # hold suspects + tap J: reveals tap-hold keys
./build_keymap.py                                   # captures -> keymap layers (C source)
```

Laptop-keyboard controls while capturing: `s` position absent, `n` key sends nothing, `b` back,
`q` quit. Results save after every key and a re-run resumes.

Things learned the hard way, all handled in the script:

- hidapi opens devices exclusively on macOS by default, and macOS never lets a process seize a
  keyboard: `open failed` even with Input Monitoring. Keyboard interfaces are opened shared.
- The board reports keys on more than one interface; held-key state is tracked per interface,
  or an empty report on one looks like a release of a key held on another.
- A quick tap can go down and up between two polls; presses are read from the event log.
- Typing on the board into another app was recorded as captures; presses only count while the
  script's own app is frontmost.
- After a `QK_BOOT` the board re-enumerates, and the old handles go silent without erroring.
  The script relaunches it with `dfu-programmer launch` and reopens when the device paths change.
- The `matrix` field in capture files is the on-screen slot, not the wiring. `build_keymap.py`
  assigns keys by physical order within each row.

`captures/debug.log` is a local diagnostic and is gitignored.
