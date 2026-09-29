; Key codes can be found here: https://wiki.osdev.org/PS/2_Keyboard
; Key names can be found here:
;   https://manpages.ubuntu.com/manpages/focal/man7/virkeycode-linux.7.html
;
; The codes defined in this file are based on ASCII, extended to cover
; all keys that can be typed on a PS/2 keyboard. The following features
; of the code set are available:
; * When the 2 most significant bits of the code are 10, the code is from
;   the numeric keypad and the lower 6 bits match the ASCII of the characters
; * When the 2 most significant bits of the code are 11, the code is a
;   non-ASCII code, with the decimal values of the lower 6 bits starting at
;   1 through 12 for F1 through F12. Other keys are assigned in this same
;   range starting after the code for F12

  .include ASCII.inc

KP_OFFSET   = %10000000
FN_OFFSET   = %11000000
MISC_OFFSET = FN_OFFSET + 13

; Key codes - a superset of ASCII
KEY_BACKSPACE    = ASCII_BACKSPACE
KEY_TAB          = ASCII_TAB
KEY_ENTER        = ASCII_LF
KEY_SPACE        = ' '
KEY_APOSTROPHE   = "'"
KEY_COMMA        = ','
KEY_MINUS        = '-'
KEY_DOT          = '.'
KEY_SLASH        = '/'
KEY_0            = '0'
KEY_1            = '1'
KEY_2            = '2'
KEY_3            = '3'
KEY_4            = '4'
KEY_5            = '5'
KEY_6            = '6'
KEY_7            = '7'
KEY_8            = '8'
KEY_9            = '9'
KEY_SEMICOLON    = ';'
KEY_EQUAL        = '='
KEY_LEFTBRACE    = '['
KEY_BACKSLASH    = '\\'
KEY_RIGHTBRACE   = ']'
KEY_GRAVE        = '`'
KEY_A            = 'a'
KEY_B            = 'b'
KEY_C            = 'c'
KEY_D            = 'd'
KEY_E            = 'e'
KEY_F            = 'f'
KEY_G            = 'g'
KEY_H            = 'h'
KEY_I            = 'i'
KEY_J            = 'j'
KEY_K            = 'k'
KEY_L            = 'l'
KEY_M            = 'm'
KEY_N            = 'n'
KEY_O            = 'o'
KEY_P            = 'p'
KEY_Q            = 'q'
KEY_R            = 'r'
KEY_S            = 's'
KEY_T            = 't'
KEY_U            = 'u'
KEY_V            = 'v'
KEY_W            = 'w'
KEY_X            = 'x'
KEY_Y            = 'y'
KEY_Z            = 'z'

KEY_F1           =  1 + FN_OFFSET
KEY_F2           =  2 + FN_OFFSET
KEY_F3           =  3 + FN_OFFSET
KEY_F4           =  4 + FN_OFFSET
KEY_F5           =  5 + FN_OFFSET
KEY_F6           =  6 + FN_OFFSET
KEY_F7           =  7 + FN_OFFSET
KEY_F8           =  8 + FN_OFFSET
KEY_F9           =  9 + FN_OFFSET
KEY_F10          = 10 + FN_OFFSET
KEY_F11          = 11 + FN_OFFSET
KEY_F12          = 12 + FN_OFFSET

KEY_KP0          = '0' + KP_OFFSET
KEY_KP1          = '1' + KP_OFFSET
KEY_KP2          = '2' + KP_OFFSET
KEY_KP3          = '3' + KP_OFFSET
KEY_KP4          = '4' + KP_OFFSET
KEY_KP5          = '5' + KP_OFFSET
KEY_KP6          = '6' + KP_OFFSET
KEY_KP7          = '7' + KP_OFFSET
KEY_KP8          = '8' + KP_OFFSET
KEY_KP9          = '9' + KP_OFFSET
KEY_KPSLASH      = '/' + KP_OFFSET
KEY_KPASTERISK   = '*' + KP_OFFSET
KEY_KPMINUS      = '-' + KP_OFFSET
KEY_KPPLUS       = '+' + KP_OFFSET
KEY_KPDOT        = '.' + KP_OFFSET
KEY_KPENTER      = ASCII_LF + KP_OFFSET

KEY_ESC          =  0 + MISC_OFFSET

KEY_LEFTCTRL     =  1 + MISC_OFFSET
KEY_LEFTSHIFT    =  2 + MISC_OFFSET
KEY_LEFTALT      =  3 + MISC_OFFSET
KEY_LEFTMETA     =  4 + MISC_OFFSET ; Left Windows / GUI
KEY_RIGHTCTRL    =  5 + MISC_OFFSET
KEY_RIGHTSHIFT   =  6 + MISC_OFFSET
KEY_RIGHTALT     =  7 + MISC_OFFSET
KEY_RIGHTMETA    =  8 + MISC_OFFSET ; Right Windows / GUI
KEY_MENU         =  9 + MISC_OFFSET

KEY_NUMLOCK      = 10 + MISC_OFFSET
KEY_CAPSLOCK     = 11 + MISC_OFFSET
KEY_SCROLLLOCK   = 12 + MISC_OFFSET

KEY_SYSRQ        = 13 + MISC_OFFSET ; Print Screen. Alt+Print Screen (SysRq) sends a different
                                    ; PS/2 code, which also translates to KEY_SYSRQ, with Alt set
KEY_PAUSE        = 14 + MISC_OFFSET ; Pause. Ctrl+Pause (Break) sends a different PS/2 code,
                                    ; which also translates to KEY_PAUSE, with Ctrl set. Plain
                                    ; Pause has no key up event: the keyboard sends its make and
                                    ; break codes together as soon as the key is pressed

KEY_LEFT         = 15 + MISC_OFFSET
KEY_RIGHT        = 16 + MISC_OFFSET
KEY_UP           = 17 + MISC_OFFSET
KEY_DOWN         = 18 + MISC_OFFSET
KEY_PAGEUP       = 19 + MISC_OFFSET
KEY_PAGEDOWN     = 20 + MISC_OFFSET
KEY_HOME         = 21 + MISC_OFFSET
KEY_END          = 22 + MISC_OFFSET
KEY_INSERT       = 23 + MISC_OFFSET
KEY_DELETE       = 24 + MISC_OFFSET

KEY_PREVIOUSSONG = 25 + MISC_OFFSET
KEY_PLAYPAUSE    = 26 + MISC_OFFSET
KEY_STOPCD       = 27 + MISC_OFFSET
KEY_NEXTSONG     = 28 + MISC_OFFSET
KEY_MUTE         = 29 + MISC_OFFSET
KEY_VOLUMEDOWN   = 30 + MISC_OFFSET
KEY_VOLUMEUP     = 31 + MISC_OFFSET
KEY_POWER        = 32 + MISC_OFFSET
KEY_SLEEP        = 33 + MISC_OFFSET
KEY_WAKE         = 34 + MISC_OFFSET
