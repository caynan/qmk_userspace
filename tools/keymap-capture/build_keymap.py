#!/usr/bin/env python3
"""Turn the capture files into a QMK keymap.c for the DZ60 (LAYOUT_directional, 2u Backspace).

Captures record what each physical key *sends*. Behaviour a tap cannot show (tap-hold, layer
keys, Space Cadet) comes from the hold test and is applied through OVERRIDES below, each with the
evidence that justifies it. Positions are assigned by physical order per row, because the capture
tool's "matrix" field is only the on-screen slot it highlighted, not the real wiring.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.join(HERE, "captures")
LAYOUT = "LAYOUT_directional"

# Mouse report = [buttons, x, y, wheel, pan] as signed bytes.
def mouse_keycode(hexstr):
    b = bytes.fromhex(hexstr)
    s = lambda v: v - 256 if v > 127 else v
    buttons, x, y, wheel = b[0], s(b[1]), s(b[2]), s(b[3])
    if buttons:
        return f"MS_BTN{buttons.bit_length()}"
    if y < 0: return "MS_UP"
    if y > 0: return "MS_DOWN"
    if x < 0: return "MS_LEFT"
    if x > 0: return "MS_RGHT"
    if wheel > 0: return "MS_WHLU"
    if wheel < 0: return "MS_WHLD"
    raise ValueError(hexstr)


def keycode(entry):
    if entry is None or entry.get("absent"):
        return "KC_NO"
    if entry["short"] == "RESET?":
        return "QK_BOOT"
    if entry["short"] == "NONE":
        return "KC_NO"
    names = [t.split("|", 1)[1] for t in entry["tokens"]]
    mice = [n for n in names if n.startswith("MOUSE:")]
    if mice:
        return mouse_keycode(mice[0][6:])
    mods = [n for n in names if n in ("KC_LCTL", "KC_LSFT", "KC_LALT", "KC_LGUI", "KC_RCTL", "KC_RSFT", "KC_RALT", "KC_RGUI")]
    keys = [n for n in names if n not in mods]
    if not keys:
        return mods[0] if len(mods) == 1 else "+".join(mods)
    if len(keys) > 1:
        raise ValueError(f"ambiguous capture {entry}")
    kc = keys[0]
    for m in reversed(mods):
        kc = f"{m[3:]}({kc})"                 # KC_LSFT + KC_9 -> LSFT(KC_9)
    return kc


def physical_rows(capture_path, slot_layout):
    """Physical keys per row, in left-to-right order, skipping slots the board doesn't have."""
    kb = json.load(open(os.path.join(HERE, "dz60-keyboard.json")))["layouts"]
    slots = kb[slot_layout]["layout"]
    res = json.load(open(capture_path))["results"]
    rows = {}
    for i, p in enumerate(slots):
        e = res.get(str(i))
        if e is None:
            sys.exit(f"{capture_path}: position {i} missing")
        if not e.get("absent"):
            rows.setdefault(int(p["y"]), []).append(e)
    return rows


def to_layout(rows):
    """Map physical rows onto LAYOUT_directional's 67 arguments (row 0 has the split-Backspace pair)."""
    row0 = rows[0]
    assert len(row0) == 14, len(row0)
    out = [keycode(e) for e in row0[:13]]
    bspc = keycode(row0[13])
    out += [bspc, bspc]                      # 2u Backspace: fill both [0,13] and [0,14]
    for y, n in ((1, 14), (2, 13), (3, 14), (4, 11)):
        assert len(rows[y]) == n, (y, len(rows[y]))
        out += [keycode(e) for e in rows[y]]
    assert len(out) == 67
    return out


def main(split_enter_is_layer_tap):
    base = to_layout(physical_rows(os.path.join(CAP, "layer0.json"), "LAYOUT_all"))
    fn = to_layout(physical_rows(os.path.join(CAP, "layer1.json"), LAYOUT))
    sym = to_layout(physical_rows(os.path.join(CAP, "layer2.json"), LAYOUT))

    # LAYOUT_directional argument indices
    CAPS, LSHIFT, RSHIFT, FN, MID_SPACE, SPLIT_ENTER = 29, 42, 53, 55, 60, 61

    # Behaviour a tap cannot reveal, with the evidence for each.
    base[CAPS] = "ALL_T(KC_ESC)"     # tap sent Esc; hold test: held = Ctrl+Shift+Alt+Gui (Hyper)
    base[LSHIFT] = "SC_LSPO"         # tap sent Shift+9 "(", hold = Shift (confirmed by owner)
    base[RSHIFT] = "SC_RSPC"         # tap sent Shift+0 ")", hold = Shift (confirmed by owner)
    base[FN] = "MO(1)"               # sends nothing; holding it gives layer 1
    base[MID_SPACE] = "LT(2, KC_SPC)"  # tap sent Space; hold test: held + J = Down (layer 2's J)
    if split_enter_is_layer_tap:
        base[SPLIT_ENTER] = "LT(2, KC_ENT)"  # tap sent Enter; hold test: held + J = Down, no Enter

    layers = [base]
    for layer, own_key in ((fn, FN), (sym, MID_SPACE)):
        out = []
        for i, (kc, b) in enumerate(zip(layer, base)):
            if i == own_key:
                out.append("_______")                     # the key holding this layer
            elif i in (LSHIFT, RSHIFT, CAPS) and kc in ("LSFT(KC_9)", "RSFT(KC_0)", "KC_ESC"):
                out.append("_______")                     # tap-hold key fell through from base
            elif i in (MID_SPACE, SPLIT_ENTER) and kc in ("KC_SPC", "KC_ENT"):
                out.append("_______")
            elif kc == b:
                out.append("_______")                     # same as base: transparent
            else:
                out.append(kc)
        layers.append(out)
    return layers


ROW_SIZES = (15, 14, 13, 14, 11)


def render_c(layers, names):
    lines = []
    for n, (name, keys) in enumerate(zip(names, layers)):
        w = max(len(k) for k in keys) + 1
        rows, i = [], 0
        for size in ROW_SIZES:
            rows.append("        " + " ".join(f"{k + ',':<{w}}" for k in keys[i:i + size]).rstrip())
            i += size
        rows[-1] = rows[-1].rstrip(",")
        body = "\n".join(rows).rstrip().rstrip(",")
        lines.append(f"    /* {n}: {name} */\n    [{n}] = {LAYOUT}(\n{body}\n    ),")
    return "\n\n".join(lines)


if __name__ == "__main__":
    split_lt = "--split-enter-plain" not in sys.argv
    layers = main(split_lt)
    names = ["Base", "Fn (hold the key right of Up)", "Mouse, arrows, media (hold the middle space key)"]
    print(render_c(layers, names))
