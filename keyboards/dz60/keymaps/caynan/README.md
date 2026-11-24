# DZ60 keymap (caynan)

KBDFans DZ60 with a split space bar (2.25u / 1.25u / 2.75u), a split right Shift carrying the
Up arrow, a 2u Backspace, and an arrow cluster in the bottom-right corner. Uses
`LAYOUT_directional`; both halves of that layout's split Backspace are set to `KC_BSPC`, since
the 2u key sits on one of them.

## Layers

| Layer | Held key | Contents |
|---|---|---|
| 0 Base | — | ANSI letters. Caps Lock position is `ALL_T(KC_ESC)` (tap Esc, hold Hyper). Shifts are Space Cadet (`SC_LSPO` / `SC_RSPC`). Middle space and the right-hand Enter are both `LT(2, …)`. |
| 1 Fn | key right of Up | `QK_BOOT` on Esc **and** on Backslash, `KC_B` on Tab, everything from C onwards empty. |
| 2 | middle space or the split Enter | F1–F12 on the number row, mouse on the left hand (`Q W E R` / `A S D F`), arrows on `H J K L`, Print Screen on P, media on the right of the bottom two rows. |

Hold Fn and press Esc to flash.

## How this was recovered

The original source was lost. The DZ60's ATmega32U4 runs Atmel's DFU bootloader, which sets
its security bit on every flash; `dfu-programmer read` then fails with `Memory read error`, and
only a chip erase clears the bit. So the keymap could not be dumped.

Instead it was captured from the outside with `tools/keymap-capture/capture.py`, which reads the
board's HID reports directly (keyboard, consumer/system and mouse interfaces), walks every key
position, and records what each one sends: once per layer while holding that layer's key. A
separate hold test (hold the key, tap J) exposed tap-hold behaviour that a single tap cannot
show. `tools/keymap-capture/build_keymap.py` turns the capture files into the layers in
`keymap.c`; every override it applies on top of the raw captures cites the evidence for it.

## What the capture cannot tell apart

- **Transparent vs. explicit.** A key on layer 1 or 2 that sent the same code as base is written
  as `_______`. The original may have repeated the base keycode explicitly, which behaves the same.
- **Empty vs. something invisible.** `KC_NO` means the key sent no HID report with the layer held.
  A key bound to a non-HID action (backlight, RGB, a layer toggle, EEPROM reset) would also send
  nothing. That applies to layer 1 from C onwards and to Z and X on layer 2. If one of them
  used to toggle the backlight or RGB, put the right keycode back.
- **Which reset.** Fn+Esc and Fn+Backslash each made the board drop off USB. Both are written as
  `QK_BOOT`; one of them may have been a different reboot-type key.
- **Timing.** Tapping term and other `config.h` options are back at QMK defaults. The old
  firmware's values are not observable.
- **USB IDs.** The old firmware enumerated as `FEED:2260`. Current QMK's dz60 uses `445A:2260`,
  which is what this keymap builds with.

## Building

From the userspace root, with `qmk config user.overlay_dir="$(pwd)"` set once:

```sh
qmk compile -kb dz60 -km caynan
qmk flash   -kb dz60 -km caynan   # then press Fn+Esc
```

VIA is enabled (`rules.mk`), so after this flash the keymap lives in EEPROM and the VIA app can
read and back it up over USB.
