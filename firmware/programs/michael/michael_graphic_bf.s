  .include base_config_v2.inc

GC_PROMPT_CHAR = '$'

;TODO ran into a bug that I can't recreate: scrolled past bottom; entered several
;lines of text; backspaced and it didn't stop at the cursor start position

INTERRUPT_ROUTINE        = INTERRUPT_VECTOR_TARGET

; Zero page allocations
GCF_ZERO_PAGE_BASE       = $00
BF_ZERO_PAGE_BASE        = GCF_ZERO_PAGE_STOP

bf_getchar               = gc_getchar
bf_putchar               = gc_putchar

; Other memory allocations
; These are from the non-BBC  Michael version where code loaded at $2000
;SIMPLE_BUFFER            = $0200 ; 256 bytes
;GC_LINE_BUFFER           = $3f00 ; GD_CHAR_ROWS * GD_CHAR_COLS = 400 bytes including terminating 0

;bf_cells                 = GC_LINE_BUFFER_STOP
;bf_cellsEnd              = bf_cells + 1024
;bf_code                  = bf_cellsEnd
;bf_codeEnd               = $2000

; Memory map (BBC version of Michael)
; $0200-$03ff - graphics line buffer (400 bytes)
; $0400-$07ff - bf cells
; $0800-$08ff - interrupt handler
; $0900-$26ff - program
; $2700-$3eff - bf compiled code ($1800 bytes)
; $3f00-$3fff - simple buffer (keyboard)

GC_LINE_BUFFER            = $0200
bf_cells                  = $0400
bf_code                   = $2700
SIMPLE_BUFFER             = $3f00

bf_cellsEnd               = bf_cells + 1024
bf_codeEnd                = $7f00

  .org PROGRAM_LOAD_ADDRESS      ; Loader loads programs to this address
  jmp initialize_machine         ; Initialize hardware and then jump to program_start

  ; The initialize_machine routine in this include will set up hardware registers and then
  ; jump to program_start. We do not call a subroutine because for some machine designs the
  ; stack is not usable until after the hardware registers have been initialized
  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include graphics_console_full.inc
  .include bf_compiler.inc


CT_COMMANDS:
  ct_entry doHello,      "hello"
  ct_entry doSierpinski, "sierpinski"
  ct_entry doGolden,     "golden"
  ct_entry doFibonacci,  "fibonacci"
  ct_entry doLife,       "life"
  .byte 0

 
doHello:
	; The classic hello world program.
	bf_compile_and_run helloWorld

doSierpinski:
	; The Sierpinski triangle program.
	bf_compile_and_run sierpinski

doGolden:
	; The Golden ratio program.
	bf_compile_and_run golden

doFibonacci:
	; The fibonacci program.
	bf_compile_and_run fibonacci

doLife:
	; The Conway game of life program.
	bf_compile_and_run life


;
; Sample programs
;

; Simple hello world program
helloWorld:
	.byte "++++++++"
	.byte "[>++++[>++>+++>+++>+<<<<-]>+>+>->>+[<]<-]"
	.byte ">>.>---.+++++++..+++.>>.<-.<.+++."
	.byte "------.--------.>>+.>++."
	.byte 0


; Fibonacci number generator by Daniel B Cristofani
; This program doesn't terminate; you will have to kill it.
fibonacci:
	.byte ">++++++++++>+>+["
	.byte "[+++++[>++++++++<-]>.<++++++[>--------<-]+<<<]>.>>["
        .byte "[-]<[>+<-]>>[<<+>+>-]<[>+<-[>+<-[>+<-[>+<-[>+<-[>+<-"
        .byte "[>+<-[>+<-[>+<-[>[-]>+>+<<<-[>+<-]]]]]]]]]]]+>>>"
	.byte "]<<<"
	.byte "]", 0


; Shows an ASCII representation of the Sierpinski triangle
; (c) 2016 Daniel B. Cristofani
sierpinski:
	.byte "++++++++[>+>++++<<-]>++>>+<[-[>>+<<-]+>>]>+["
	.byte "-<<<["
	.byte "->[+[-]+>++>>>-<<]<[<]>>++++++[<<+++++>>-]+<<++.[-]<<"
	.byte "]>.>+[>>]>+"
	.byte "]", 0


; Compute the "golden ratio". Because this number is infinitely long,
; this program doesn't terminate on its own. You will have to kill it.
golden:
	.byte "+>>>>>>>++>+>+>+>++<["
	.byte "  +["
	.byte "    --[++>>--]->--["
	.byte "      +["
	.byte "        +<+[-<<+]++<<[-[->-[>>-]++<[<<]++<<-]+<<]>>>>-<<<<"
	.byte "          <++<-<<++++++[<++++++++>-]<.---<[->.[-]+++++>]>[[-]>>]"
	.byte "          ]+>>--"
	.byte "      ]+<+[-<+<+]++>>"
	.byte "    ]<<<<[[<<]>>[-[+++<<-]+>>-]++[<<]<<<<<+>]"
	.byte "  >[->>[[>>>[>>]+[-[->>+>>>>-[-[+++<<[-]]+>>-]++[<<]]+<<]<-]<]]>>>>>>>"
	.byte "]", 0


; Conways game of life
;
; Adjust the number of '+' operations inside the parenthesis () to control the dimensions
; of the board.
life:
	.byte ">>>->+>+++++>(++++++++++)[[>>>+<<<-]>+++++>+>>+[<<+>>>>>+<<<-]<-]>>>>["
	.byte "  [>>>+>+<<<<-]+++>>+[<+>>>+>+<<<-]>>[>[[>>>+<<<-]<]<<++>+>>>>>>-]<-"
	.byte "]+++>+>[[-]<+<[>+++++++++++++++++<-]<+]>>["
	.byte "  [+++++++++.-------->>>]+[-<<<]>>>[>>,----------[>]<]<<["
	.byte "    <<<["
	.byte "      >--[<->>+>-<<-]<[[>>>]+>-[+>>+>-]+[<<<]<-]>++>[<+>-]"
	.byte "      >[[>>>]+[<<<]>>>-]+[->>>]<-[++>]>[------<]>+++[<<<]>"
	.byte "    ]<"
	.byte "  ]>["
	.byte "    -[+>>+>-]+>>+>>>+>[<<<]>->+>["
	.byte "      >[->+>+++>>++[>>>]+++<<<++<<<++[>>>]>>>]<<<[>[>>>]+>>>]"
	.byte "      <<<<<<<[<<++<+[-<<<+]->++>>>++>>>++<<<<]<<<+[-<<<+]+>->>->>"
	.byte "    ]<<+<<+<<<+<<-[+<+<<-]+<+["
	.byte "      ->+>[-<-<<[<<<]>[>>[>>>]<<+<[<<<]>-]]"
	.byte "      <[<[<[<<<]>+>>[>>>]<<-]<[<<<]]>>>->>>[>>>]+>"
	.byte "    ]>+[-<<[-]<]-["
	.byte "      [>>>]<[<<[<<<]>>>>>+>[>>>]<-]>>>[>[>>>]<<<<+>[<<<]>>-]>"
	.byte "    ]<<<<<<[---<-----[-[-[<->>+++<+++++++[-]]]]<+<+]>"
	.byte "  ]>>"
	.byte "]", 0


program_start:
  ; Initialize stack
  ldx #$ff
  txs

  jsr gcf_init

  jsr doLife
  jmp cr_repl


.end_of_program:
;  .assert INTERRUPT_ROUTINE >= .end_of_program, "Program is too long"
  .assert bf_code >= .end_of_program, "Program is too long"
