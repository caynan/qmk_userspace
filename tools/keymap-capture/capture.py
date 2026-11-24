#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["hidapi"]
# ///
"""Guided per-key capture of a QMK keyboard's output, read straight from its HID reports.

Used to recover a keymap from a board whose flash is read-locked (Atmel DFU sets the security
bit on every flash, and only a chip erase clears it).

Walks every position of a QMK layout, highlights it on an ASCII map, and records what the
keyboard sends when you press it. One run captures one layer: for layer 1+, hold that layer's
key with one hand while pressing positions with the other.

Needs macOS Input Monitoring for the terminal that runs it, otherwise the keyboard interfaces
refuse to open.

Laptop-keyboard controls (typed while this runs; keystrokes from the target board are ignored):
  s  position not present on your board     n  key exists but sends nothing
  b  go back one position                   q  save and quit
Re-running with the same --out resumes where you stopped.
"""
import argparse, json, os, select, subprocess, sys, termios, threading, time, tty

import ctypes

import hid

VID, PID = 0xFEED, 0x2260

# hidapi on macOS opens devices exclusively (IOHIDDeviceOpen with seize) by default, and macOS
# refuses to let any process seize a keyboard, so the keyboard interfaces must open shared.
# The media/system and mouse interfaces stay seized on purpose: a power or sleep key on some
# layer then reaches only this script, not macOS.
_HIDLIB = ctypes.CDLL(hid.__file__)


def set_exclusive(on):
    _HIDLIB.hid_darwin_set_open_exclusive(1 if on else 0)

HID_NAMES = {
    **{0x04 + i: f"KC_{chr(ord('A') + i)}" for i in range(26)},
    **{0x1E + i: f"KC_{(i + 1) % 10}" for i in range(10)},
    0x28: "KC_ENT", 0x29: "KC_ESC", 0x2A: "KC_BSPC", 0x2B: "KC_TAB", 0x2C: "KC_SPC",
    0x2D: "KC_MINS", 0x2E: "KC_EQL", 0x2F: "KC_LBRC", 0x30: "KC_RBRC", 0x31: "KC_BSLS",
    0x32: "KC_NUHS", 0x33: "KC_SCLN", 0x34: "KC_QUOT", 0x35: "KC_GRV", 0x36: "KC_COMM",
    0x37: "KC_DOT", 0x38: "KC_SLSH", 0x39: "KC_CAPS",
    **{0x3A + i: f"KC_F{i + 1}" for i in range(12)},
    0x46: "KC_PSCR", 0x47: "KC_SCRL", 0x48: "KC_PAUS", 0x49: "KC_INS", 0x4A: "KC_HOME",
    0x4B: "KC_PGUP", 0x4C: "KC_DEL", 0x4D: "KC_END", 0x4E: "KC_PGDN", 0x4F: "KC_RGHT",
    0x50: "KC_LEFT", 0x51: "KC_DOWN", 0x52: "KC_UP", 0x53: "KC_NUM", 0x54: "KC_PSLS",
    0x55: "KC_PAST", 0x56: "KC_PMNS", 0x57: "KC_PPLS", 0x58: "KC_PENT",
    **{0x59 + i: f"KC_P{(i + 1) % 10}" for i in range(10)},
    0x63: "KC_PDOT", 0x64: "KC_NUBS", 0x65: "KC_APP", 0x66: "KC_KB_POWER", 0x67: "KC_PEQL",
    **{0x68 + i: f"KC_F{13 + i}" for i in range(12)},
    0x7F: "KC_KB_MUTE", 0x80: "KC_KB_VOLUME_UP", 0x81: "KC_KB_VOLUME_DOWN",
    0xE0: "KC_LCTL", 0xE1: "KC_LSFT", 0xE2: "KC_LALT", 0xE3: "KC_LGUI",
    0xE4: "KC_RCTL", 0xE5: "KC_RSFT", 0xE6: "KC_RALT", 0xE7: "KC_RGUI",
}
CONSUMER = {0xE2: "KC_MUTE", 0xE9: "KC_VOLU", 0xEA: "KC_VOLD", 0xB5: "KC_MNXT", 0xB6: "KC_MPRV",
            0xB7: "KC_MSTP", 0xCD: "KC_MPLY", 0xB8: "KC_EJCT", 0x183: "KC_MSEL", 0x18A: "KC_MAIL",
            0x192: "KC_CALC", 0x194: "KC_MYCM", 0x221: "KC_WSCH", 0x223: "KC_WHOM", 0x224: "KC_WBAK",
            0x225: "KC_WFWD", 0x226: "KC_WSTP", 0x227: "KC_WREF", 0x22A: "KC_WFAV", 0xB3: "KC_MFFD",
            0xB4: "KC_MRWD", 0x6F: "KC_BRIU", 0x70: "KC_BRID", 0x29F: "KC_MCTL", 0x2A0: "KC_LPAD"}
SYSTEM = {0x81: "KC_PWR", 0x82: "KC_SLEP", 0x83: "KC_WAKE"}
MOD_BITS = ["KC_LCTL", "KC_LSFT", "KC_LALT", "KC_LGUI", "KC_RCTL", "KC_RSFT", "KC_RALT", "KC_RGUI"]


def front_app():
    """Name of the frontmost macOS app, via lsappinfo (no extra permissions needed)."""
    out = subprocess.run(["lsappinfo", "info", "-only", "name", subprocess.run(
        ["lsappinfo", "front"], capture_output=True, text=True).stdout.strip()], capture_output=True, text=True).stdout
    return out.split('"')[1] if out.count('"') >= 2 else ""


class FocusGate:
    """Only the app this script runs in counts: DZ60 typing into any other app is not a capture."""

    def __init__(self):
        self.app = front_app()
        self.checked, self.ok = 0.0, True

    def focused(self):
        now = time.monotonic()
        if now - self.checked > 0.3:
            self.ok, self.checked = front_app() == self.app, now
        return self.ok


GATE = None


class Board:
    """Reads every openable interface of the board on its own thread and keeps a press log."""

    def __init__(self):
        self.lock = threading.Lock()
        self.events = []          # (time, kind, tokens, raw_hex)
        self.last_activity = 0.0   # any report, including empty ones
        self.last_press = 0.0      # reports with at least one key down
        self.down = set()          # currently-held tokens, to detect full release
        self.gone = False
        self.unopenable = []
        self.threads = []
        self.open_all()
        debug(f"Board opened: threads={len(self.threads)} unopenable={self.unopenable}")

    def open_all(self):
        by_path = {}                                          # one path per USB interface; several usages share it
        for d in hid.enumerate(VID, PID):
            by_path.setdefault(d["path"], set()).add((d["usage_page"], d["usage"]))
        self.paths = set(by_path)
        for n, (path, usages) in enumerate(by_path.items()):
            page, usage = (1, 6) if (1, 6) in usages else (1, 2) if (1, 2) in usages else (0x0C, 1)
            h = hid.device()
            set_exclusive(page != 0x01 or usage != 0x06)
            try:
                h.open_path(path)
            except OSError:
                self.unopenable.append(sorted(usages))
                continue
            t = threading.Thread(target=self.reader, args=(h, page, usage, n), daemon=True)
            t.start()
            self.threads.append(t)

    def reader(self, h, page, usage, iface):
        state = {}
        while True:
            try:
                data = h.read(64, 100)
            except (OSError, ValueError):
                with self.lock:
                    self.gone = True
                return
            if data:
                self.decode(page, usage, bytes(data), state, iface)

    def decode(self, page, usage, data, state, iface=0):
        now = time.monotonic()
        tokens = set()
        if page == 0x01 and usage == 0x06:                     # keyboard: boot (8 bytes) or NKRO bitmap
            kind = "kbd"
            mods = data[0]
            tokens |= {MOD_BITS[i] for i in range(8) if mods & (1 << i)}
            if len(data) == 8:
                tokens |= {HID_NAMES.get(b, f"0x{b:02X}") for b in data[2:] if b}
            else:
                for byte_i, b in enumerate(data[1:]):
                    for bit in range(8):
                        if b & (1 << bit):
                            code = byte_i * 8 + bit
                            tokens.add(HID_NAMES.get(code, f"0x{code:02X}"))
        elif page == 0x01 and usage == 0x02:                   # mouse keys
            kind = "mouse"
            if any(data):
                tokens.add("MOUSE:" + data.hex())
        else:                                                  # extrakey: report id + 16-bit usage
            kind = "extra"
            rid = data[0]
            state[rid] = int.from_bytes(data[1:3], "little") if len(data) >= 3 else 0
            for r, v in state.items():
                if v:
                    tokens.add(CONSUMER.get(v) or SYSTEM.get(v) or f"USAGE:rid{r}:0x{v:X}")
        kind = f"{kind}{iface}"   # per interface: an empty report on one must not clear keys held on another
        if tokens and GATE is not None and not GATE.focused():
            return                                             # typed into another app: ignore entirely
        with self.lock:
            self.last_activity = now
            if tokens:
                self.last_press = now
            self.down = {t for t in self.down if not t.startswith(kind + "|")} | {f"{kind}|{t}" for t in tokens}
            if tokens:
                self.events.append((now, kind, sorted(tokens), data.hex()))

    def stale(self):
        """True when the board re-enumerated (e.g. after RESET) and our handles point at the old device.

        A stale handle raises no error, it just never delivers data, so compare paths instead.
        """
        current = {d["path"] for d in hid.enumerate(VID, PID)}
        return bool(current) and current != self.paths

    def snapshot(self):
        with self.lock:
            return len(self.events), set(self.down), self.gone


DEBUG_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures", "debug.log")


def debug(msg):
    with open(DEBUG_LOG, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def wait_present(timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if hid.enumerate(VID, PID):
            return True
        time.sleep(0.5)
    return False


def render(positions, idx, results):
    rows = {}
    for i, p in enumerate(positions):
        rows.setdefault(int(p["y"]), []).append((i, p))
    out = []
    for y in sorted(rows):
        line = ""
        for i, p in rows[y]:
            x, w = p["x"], p.get("w", 1)
            line = line.ljust(round(x * 6)) if i != idx else line
            cell_w = max(3, round(w * 6) - 1)
            if i == idx:
                line = line + " " * max(0, round(x * 6) - len(strip_ansi(line)))
                line += "\033[7;1m[" + "##".center(cell_w - 2) + "]\033[0m"
                continue
            r = results.get(str(i))
            txt = "." if r is None else r["short"]
            pad = round(x * 6) - len(strip_ansi(line))
            line += " " * max(0, pad) + "[" + txt[: cell_w - 2].center(cell_w - 2) + "]"
        out.append(line)
    return "\n".join(out)


def strip_ansi(s):
    out, skip = [], False
    for ch in s:
        if ch == "\033":
            skip = True
        elif skip and ch == "m":
            skip = False
        elif not skip:
            out.append(ch)
    return "".join(out)


def short(tokens):
    names = [t.split("|", 1)[1] for t in tokens]
    keys = [n.replace("KC_", "") for n in names if n not in MOD_BITS]
    mods = [n.replace("KC_", "") for n in names if n in MOD_BITS]
    return "+".join(mods + keys) if keys or mods else "?"


def relaunch_from_bootloader():
    for _ in range(20):
        if subprocess.run(["dfu-programmer", "atmega32u4", "launch"], capture_output=True).returncode == 0:
            return True
        time.sleep(0.5)
    return False


HOLD_SUSPECTS = [0, 15, 28, 29, 39, 40, 41, 59, 60, 61]   # LAYOUT_directional: Esc Tab \ Caps ; ' Enter Spc Spc Enter


def laptop_key(fd, board, settle=0.35):
    """Next stdin char that came from the laptop keyboard, not echoed from the board; None if none waiting.

    settle=0 skips the board-origin check, for prompts whose answers the tested keys can never type.
    """
    if not select.select([fd], [], [], 0)[0]:
        return None
    ch = os.read(fd, 1).decode(errors="ignore")
    if not settle:
        return ch
    t = time.monotonic()
    time.sleep(settle)
    with board.lock:
        from_board = board.last_press >= t - 0.5
    return None if from_board else ch


def hold_test(positions, indices, out_path):
    """Reveal tap-hold keys: hold the highlighted key, tap J, release both.

    Nothing advances on its own: after each attempt the recorded report states are shown and you
    accept (y) or redo (r) from the laptop keyboard.
    """
    board = Board()
    results = json.load(open(out_path)) if os.path.exists(out_path) else {}
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    try:
        i = 0
        while i < len(indices):
            idx = indices[i]
            if str(idx) in results:
                i += 1
                continue
            sys.stdout.write("\033[2J\033[H")
            print(f"Hold test  {i + 1}/{len(indices)}  matrix {positions[idx]['matrix']}\n")
            print(render(positions, idx, {}))
            print("\nHold the highlighted key ~1 second, tap J while holding it, then release.")
            print("Recording... (laptop: d = done recording, q = quit)")
            sys.stdout.flush()
            n0, _, _ = board.snapshot()
            seq = []
            while True:
                _, down, _ = board.snapshot()
                state = sorted(t.split("|", 1)[1] for t in down)
                if state and (not seq or seq[-1] != state) or (seq and not state and seq[-1]):
                    seq.append(state)
                ch = laptop_key(fd, board, 0.05) if select.select([fd], [], [], 0.02)[0] else None
                if ch == "q":
                    return
                if ch == "d" or (seq and not state and time.monotonic() - board.last_activity > 1.5):
                    break
            with board.lock:
                raw = [(round(t, 3), k, toks, h) for t, k, toks, h in board.events[n0:]]
            print("\nRecorded states:")
            for st in seq:
                print("   ", " + ".join(x.replace("KC_", "") for x in st) or "(all released)")
            print("\nLaptop: y = keep and go to next key,  r = redo this key,  q = quit")
            sys.stdout.flush()
            while True:
                ch = laptop_key(fd, board, 0)
                if ch in ("y", "r", "q"):
                    break
                time.sleep(0.05)
            if ch == "q":
                return
            if ch == "y":
                results[str(idx)] = {"matrix": positions[idx]["matrix"], "sequence": seq, "raw": raw}
                with open(out_path, "w") as f:
                    json.dump(results, f, indent=1)
                i += 1
        sys.stdout.write("\033[2J\033[H")
        print(f"Hold test complete -> {out_path}")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def main():
    global GATE
    GATE = FocusGate()
    here = os.path.dirname(os.path.abspath(__file__))
    if "--hold-test" in sys.argv:
        positions = json.load(open(os.path.join(here, "dz60-keyboard.json")))["layouts"]["LAYOUT_directional"]["layout"]
        hold_test(positions, HOLD_SUSPECTS, os.path.join(here, "captures", "hold-test.json"))
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyboard-json", default=os.path.join(here, "dz60-keyboard.json"))
    ap.add_argument("--layout", default="LAYOUT_all")
    ap.add_argument("--layer", type=int, required=True)
    ap.add_argument("--out", help="default: captures/layer<N>.json next to this script")
    ap.add_argument("--settle", type=float, default=0.35, help="seconds to wait for HID before trusting a laptop key")
    args = ap.parse_args()
    out_path = args.out or os.path.join(here, "captures", f"layer{args.layer}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    positions = json.load(open(args.keyboard_json))["layouts"][args.layout]["layout"]
    results = json.load(open(out_path)).get("results", {}) if os.path.exists(out_path) else {}
    board = Board()
    if board.unopenable:
        print(f"Cannot open keyboard interfaces {board.unopenable}: grant Input Monitoring to this terminal, then restart it.")
        sys.exit(2)

    def save():
        with open(out_path, "w") as f:
            json.dump({"layout": args.layout, "layer": args.layer, "results": results}, f, indent=1)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    idx = next((i for i in range(len(positions)) if str(i) not in results), len(positions))
    try:
        while args.layer >= 1 and idx == 0:                    # make sure the held key really is a layer key
            sys.stdout.write("\033[2J\033[H")
            print(f"Layer {args.layer}: hold this layer's key on the board, then press g on the laptop.  q=quit")
            sys.stdout.flush()
            ch = laptop_key(fd, board, 0)
            if ch is None:
                time.sleep(0.05)
                continue
            if ch == "q":
                return
            if ch != "g":
                continue
            _, down, _ = board.snapshot()
            if not down:
                break
            print(f"\nThe key you are holding sends {short(down)}, so it is not a layer key. "
                  "Hold a different key, then press any laptop key to retry.")
            sys.stdout.flush()
            while laptop_key(fd, board, 0) is None:
                time.sleep(0.05)
        while idx < len(positions):
            p = positions[idx]
            sys.stdout.write("\033[2J\033[H")
            print(f"Layer {args.layer}  position {idx + 1}/{len(positions)}  matrix {p['matrix']}\n")
            print(render(positions, idx, results))
            print("\nPress the highlighted key on the board.  Laptop keys: s=not present  n=sends nothing  b=back  q=quit")
            sys.stdout.flush()
            n0, _, _ = board.snapshot()
            pressed, decided, went_back = set(), None, False
            last_check = time.monotonic()
            while decided is None and not went_back:
                r, _, _ = select.select([fd], [], [], 0.05)
                if time.monotonic() - last_check > 1:
                    last_check = time.monotonic()
                    if board.stale():
                        debug("board handles stale; reopening")
                        board = Board()
                        n0, _, _ = board.snapshot()
                n, down, gone = board.snapshot()
                if gone:                                       # board dropped off USB: almost certainly RESET
                    decided = {"tokens": [], "short": "RESET?", "note": "board disconnected"}
                    print("\nBoard disconnected (RESET?). Relaunching from bootloader...")
                    relaunch_from_bootloader()
                    if not wait_present(30):
                        results[str(idx)] = {**decided, "matrix": p["matrix"]}
                        save()
                        print("Board did not come back. Replug it, then re-run to resume.")
                        return
                    time.sleep(3)
                    board = Board()
                    break
                if n > n0:
                    # Build the press from the event log, not from polling `down`: a quick tap can go
                    # down and up between two polls, which used to leave the position stuck forever.
                    with board.lock:
                        pressed = {f"{k}|{t}" for _, k, toks, _ in board.events[n0:] for t in toks}
                    if not down and pressed:                   # full release after a press
                        decided = {"tokens": sorted(pressed), "short": short(pressed)}
                        time.sleep(0.15)
                        while select.select([fd], [], [], 0)[0]:  # swallow the board's own keystrokes from stdin
                            os.read(fd, 64)
                        break
                if r:
                    t_char = time.monotonic()
                    ch = os.read(fd, 1).decode(errors="ignore")
                    time.sleep(args.settle)
                    n2, _, _ = board.snapshot()
                    with board.lock:
                        recent = board.last_press >= t_char - 0.5
                    with board.lock:
                        age = time.monotonic() - board.last_press
                        tail = board.events[-3:]
                    alive = sum(t.is_alive() for t in board.threads)
                    debug(f"laptop {ch!r} pos={idx} n0={n0} n2={n2} press_age={age:.2f} recent={recent} "
                          f"threads_alive={alive}/{len(board.threads)} gone={board.gone} focused={GATE.focused()} "
                          f"tail={[(k, toks) for _, k, toks, _ in tail]}")
                    if recent:
                        continue                               # keystroke came from the board itself
                    if ch == "s":
                        decided = {"tokens": [], "short": "--", "absent": True}
                    elif ch == "n":
                        decided = {"tokens": [], "short": "NONE"}
                    elif ch == "b" and idx > 0:
                        idx -= 1
                        results.pop(str(idx), None)
                        save()
                        went_back = True
                    elif ch == "q":
                        save()
                        return
            if decided is not None:
                results[str(idx)] = {**decided, "matrix": p["matrix"]}
                save()
                idx = next((i for i in range(idx + 1, len(positions)) if str(i) not in results), len(positions))
        sys.stdout.write("\033[2J\033[H")
        print(render(positions, -1, results))
        print(f"\nLayer {args.layer} complete -> {out_path}")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
