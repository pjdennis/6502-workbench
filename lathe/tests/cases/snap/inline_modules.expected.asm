; module inline_modules, cpu 6502
; imports: libinline

; function inline_modules.f
;   slot 0 k: size 1, class 1 (either), param, weight 2
;   slot 1 level: size 1, class 1 (either), local, weight 2
;   slot 2 $t1: size 1, class 1 (either), temp, weight 4
;   calls libinline.report
inline_modules__f
    STA inline_modules__f__k
    CLC
    LDA libinline__level
    ADC #$03
    STA libinline__level
    STA inline_modules__f__level
    CLC
    ADC inline_modules__f__k
    STA inline_modules__f__St1
    JSR libinline__report
    LDA inline_modules__f__St1
    STA libshared__count
    CLC
    LDA libinline__level
    ADC inline_modules__f__level
    STA inline_modules__f__St1
    JSR libinline__report
    LDA inline_modules__f__St1
    STA libshared__count
    RTS

; variable inline_modules.level: size 1, class 1 (either), weight 0
