#!/usr/bin/env bash
# Draw a keymap as an SVG with keymap-drawer (https://github.com/caksoylar/keymap-drawer).
#
#   tools/draw-keymap/draw.sh            # dz60:caynan -> keyboards/dz60/keymaps/caynan/keymap.svg
#   tools/draw-keymap/draw.sh --check    # exit 1 if the committed SVG is out of date
#
# Needs the qmk CLI (for `qmk c2json`), a qmk_firmware checkout (QMK_HOME or user.qmk_home), and uv. keymap-drawer is pinned below
# and run through uvx, so nothing is installed globally.
#
# The DZ60 keymap uses LAYOUT_directional, which has a split Backspace ([0,13] and [0,14]). This
# board has a 2u Backspace, so the script draws key 13 two units wide and drops key 14 from both
# the physical layout and every layer. keymap.c fills both halves with the same keycode.
set -euo pipefail

KEYMAP_DRAWER="keymap-drawer==0.23.0"
KEYBOARD=dz60
KEYMAP=caynan
LAYOUT=LAYOUT_directional
LAYER_NAMES=(Base Fn Nav)

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
keymap_dir="$root/keyboards/$KEYBOARD/keymaps/$KEYMAP"
out="$keymap_dir/keymap.svg"
check=false
[[ ${1:-} == --check ]] && check=true

# QMK_HOME wins (CI sets it); otherwise the qmk CLI's own config.
qmk_home=${QMK_HOME:-$(qmk config -ro user.qmk_home | cut -d= -f2-)}
info_json="$qmk_home/keyboards/$KEYBOARD/keyboard.json"
[[ -f $info_json ]] || { echo "no $info_json; run qmk setup or set user.qmk_home" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

qmk c2json -kb "$KEYBOARD" -km "$KEYMAP" "$keymap_dir/keymap.c" >"$tmp/keymap.json"

# Merge the split Backspace into one 2u key, in the layout and in every layer.
python3 - "$tmp/keymap.json" "$info_json" "$LAYOUT" "$tmp" <<'PY'
import json, sys
keymap_path, info_path, layout, tmp = sys.argv[1:]
km = json.load(open(keymap_path))
for layer in km["layers"]:
    del layer[14]
json.dump(km, open(keymap_path, "w"))
info = json.load(open(info_path))
keys = info["layouts"][layout]["layout"]
keys[13]["w"] = 2
del keys[14]
json.dump({"layouts": {layout: {"layout": keys}}}, open(f"{tmp}/physical.json", "w"))
PY

kd() { uvx --quiet --from "$KEYMAP_DRAWER" keymap -c "$here/config.yaml" "$@"; }
kd parse -q "$tmp/keymap.json" -l "${LAYER_NAMES[@]}" -c 14 -o "$tmp/keymap.yaml"
# Long names for the tap half of layer-tap keys (see the LT note in config.yaml).
sed -e 's/{t: SPC, h:/{t: Space, h:/g' -e 's/{t: ENT, h:/{t: Enter, h:/g' \
  "$tmp/keymap.yaml" >"$tmp/keymap.renamed.yaml"
kd draw -j "$tmp/physical.json" -l "$LAYOUT" "$tmp/keymap.renamed.yaml" -o "$tmp/keymap.svg"

if $check; then
  if ! cmp -s "$tmp/keymap.svg" "$out"; then
    echo "$out is out of date; run tools/draw-keymap/draw.sh" >&2
    exit 1
  fi
  echo "$out is up to date"
else
  cp "$tmp/keymap.svg" "$out"
  echo "wrote $out"
fi
