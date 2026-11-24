---
name: dz60-keymap
description: Change, build, redraw, document or flash the KBDFans DZ60 keymap in this QMK userspace (keyboards/dz60/keymaps/caynan). Use when the user wants to remap a key, add or change a layer, change tap-hold behaviour, regenerate the keymap image, update the keymap README, compile the firmware, or flash the keyboard, even if they only say "my keyboard" or name a key ("make Caps Lock Ctrl").
---

# DZ60 keymap

Source of truth: `keyboards/dz60/keymaps/caynan/keymap.c` (`LAYOUT_directional`, 67 arguments
per layer). Everything else is derived from it or documents it:

| File | What it is | Kept in sync by |
|---|---|---|
| `keymap.c` | The keymap | you |
| `keymap.svg` | Image of all layers | `tools/draw-keymap/draw.sh`; CI fails when stale |
| `README.md` (keymap dir) | Layers table, flashing, recovery notes | you, by hand |
| `rules.mk` | Features (`VIA_ENABLE`) | you |
| `tools/draw-keymap/config.yaml` | Legends for the image | you, when a keycode draws badly |

## Physical layout

Five rows. Argument indices in `LAYOUT_directional` that matter:

- Row 0 (0–14): Esc, 1–0, `-`, `=`, then **13 and 14 are both Backspace**. The board has a 2u
  Backspace; both halves of the layout's split Backspace must carry the same keycode.
- Row 1 (15–28): Tab … Backslash. Row 2 (29–41): Caps position (29) … Enter.
- Row 3 (42–55): Left Shift (42), Z–/, Right Shift (53), Up (54), Fn (55).
- Row 4 (56–66): Ctrl, Opt, Cmd, left space (59), middle space (60), right space / split Enter
  (61), Cmd, Opt, Left, Down, Right.

Layer 1 (Fn) is held with index 55 (`MO(1)`). Layer 2 (Nav) is held with 60 or 61 (`LT(2, …)`).
Write `_______` for keys that should fall through to base, `KC_NO` for keys that must do nothing.

## Changing the keymap

1. Edit `keymap.c`. Keep the column alignment of the existing layers.
2. Compile: `qmk compile -kb dz60 -km caynan`. Needs `user.overlay_dir` pointing at this repo
   (`qmk config user.overlay_dir`); fix that before anything else if the keymap is not found.
3. Redraw: `tools/draw-keymap/draw.sh`. Look at the result, do not assume it: convert with
   `rsvg-convert -w 1200 keyboards/dz60/keymaps/caynan/keymap.svg -o <scratch>.png` and view
   the PNG. A keycode shown as its raw name (`RM_TOGG`, `KC_BRIU`) needs a `raw_binding_map`
   entry in `tools/draw-keymap/config.yaml`; then redraw.
4. Update the Layers table in `keyboards/dz60/keymaps/caynan/README.md` so it describes the new
   behaviour in words (tap vs hold, which key opens which layer). If a layer is added, add its
   name to `LAYER_NAMES` in `draw.sh` and a row to the table.
5. `tools/draw-keymap/draw.sh --check` must pass. Commit `keymap.c`, `keymap.svg` and the README
   together.

Pushing to `main` runs two workflows: `Build QMK firmware` (attaches `dz60_caynan.hex` to the
`latest` release) and `Keymap image` (the `--check` above). Pass `--repo caynan/qmk_userspace`
to every `gh` command here: this clone's `gh` default repo is upstream `qmk/qmk_userspace`, so a
bare `gh run list` shows upstream's runs and makes it look as if the push triggered nothing.

## Flashing

Flashing is irreversible: it erases the board, and the DZ60's Atmel DFU bootloader keeps its
security bit set, so the running firmware cannot be read back or backed up. **Always confirm with
the user before flashing**, and say which firmware will be written (local build or CI hex).

- Local build: `qmk flash -kb dz60 -km caynan`. When it prints `Bootloader not found ...
  Trying again in 5s`, the user holds Fn (right of Up) and presses Esc, or presses the reset
  button under the PCB. The user has to do this; you cannot.
- CI build: `gh release download latest --repo caynan/qmk_userspace --pattern dz60_caynan.hex`,
  then `qmk flash dz60_caynan.hex`.
- After flashing, confirm the board came back: `ioreg -p IOUSB -l | grep -i dz60` or ask the user
  to type on it.

VIA is enabled. A remap done in the VIA app lives only in EEPROM; if the user did one, port it
into `keymap.c` before the next flash.

## Recovering a lost keymap

`tools/keymap-capture/` records what each key sends over HID and rebuilds `keymap.c` from it.
See its README. Only needed if `keymap.c` and the board ever disagree again.
