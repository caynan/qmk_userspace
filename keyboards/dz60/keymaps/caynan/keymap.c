// Copyright 2026 Caynan Sousa
// SPDX-License-Identifier: GPL-2.0-or-later
//
// KBDFans DZ60: split space, split right Shift with arrows, 2u Backspace.
//
// Recovered on 2026-11-23 from the running firmware after the original source was lost. The
// flash is read-locked (Atmel DFU sets the security bit), so every key was captured live from
// its HID reports with tools/keymap-capture/. Tap-hold behaviour came from a separate hold test.
// See README.md beside this file for the evidence and what remains uncertain.

#include QMK_KEYBOARD_H

const uint16_t PROGMEM keymaps[][MATRIX_ROWS][MATRIX_COLS] = {
    /* 0: Base */
    [0] = LAYOUT_directional(
        KC_ESC,        KC_1,          KC_2,          KC_3,          KC_4,          KC_5,          KC_6,          KC_7,          KC_8,          KC_9,          KC_0,          KC_MINS,       KC_EQL,        KC_BSPC,       KC_BSPC,
        KC_TAB,        KC_Q,          KC_W,          KC_E,          KC_R,          KC_T,          KC_Y,          KC_U,          KC_I,          KC_O,          KC_P,          KC_LBRC,       KC_RBRC,       KC_BSLS,
        ALL_T(KC_ESC), KC_A,          KC_S,          KC_D,          KC_F,          KC_G,          KC_H,          KC_J,          KC_K,          KC_L,          KC_SCLN,       KC_QUOT,       KC_ENT,
        SC_LSPO,       KC_Z,          KC_X,          KC_C,          KC_V,          KC_B,          KC_N,          KC_M,          KC_COMM,       KC_DOT,        KC_SLSH,       SC_RSPC,       KC_UP,         MO(1),
        KC_LCTL,       KC_LALT,       KC_LGUI,       KC_SPC,        LT(2, KC_SPC), LT(2, KC_ENT), KC_RGUI,       KC_RALT,       KC_LEFT,       KC_DOWN,       KC_RGHT
    ),

    /* 1: Fn (hold the key right of Up) */
    [1] = LAYOUT_directional(
        QK_BOOT, _______, _______, _______, _______, _______, _______, _______, _______, _______, _______, _______, _______, _______, _______,
        KC_B,    _______, _______, _______, _______, _______, _______, _______, _______, _______, _______, _______, _______, QK_BOOT,
        _______, _______, _______, _______, _______, _______, _______, _______, _______, _______, _______, _______, _______,
        _______, _______, _______, KC_NO,   KC_NO,   KC_NO,   KC_NO,   KC_NO,   KC_NO,   KC_NO,   KC_NO,   KC_NO,   KC_NO,   _______,
        KC_NO,   KC_NO,   KC_NO,   KC_NO,   KC_NO,   KC_NO,   KC_NO,   KC_NO,   KC_NO,   KC_NO,   KC_NO
    ),

    /* 2: Mouse, arrows, media (hold the middle space key) */
    [2] = LAYOUT_directional(
        _______, KC_F1,   KC_F2,   KC_F3,   KC_F4,   KC_F5,   KC_F6,   KC_F7,   KC_F8,   KC_F9,   KC_F10,  KC_F11,  KC_F12,  _______, _______,
        _______, MS_BTN1, MS_UP,   MS_BTN2, MS_WHLU, _______, _______, _______, _______, _______, KC_PSCR, _______, _______, _______,
        _______, MS_LEFT, MS_DOWN, MS_RGHT, MS_WHLD, _______, KC_LEFT, KC_DOWN, KC_UP,   KC_RGHT, _______, _______, _______,
        _______, KC_NO,   KC_NO,   _______, _______, _______, _______, _______, _______, _______, _______, KC_MPLY, KC_VOLU, KC_MUTE,
        _______, _______, _______, _______, _______, _______, _______, _______, KC_MPRV, KC_VOLD, KC_MNXT
    ),
};
