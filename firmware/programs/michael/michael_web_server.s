; A web server: the W5500 Ethernet module on the FPGA bus (fpga_w5500.inc) answers each visit to
; http://192.168.86.251/ with a page, "Hello, world!" and a note for Angel, and the visitor's number. The LCD shows
;   WEB 192.168.86.251
;   SERVED 2               visits answered
;   GET / HTTP/1.1         the last request's first line (its first 20 characters)
;   FAULTS 0000 DROP 00    frames the FPGA reported going wrong (fpga_w5500.inc), and connections dropped for
;                          sending no request in time, in hex
; or NO W5500 if VERSIONR doesn't read $04.
;
; HTTP/1.0 on port 80, through SOCKETS of the W5500's TCP sockets, each listening, so that a connection that sends
; nothing (a browser opens some early and may never use them; a phone may go to sleep) doesn't keep others out.
; The loop goes round the sockets: a socket closed listens again; once a client is connected, what it sends is
; read until the blank line that ends its request's headers, then the page goes out (or 404, for any path but /:
; a browser asks for /favicon.ico too) and the connection is ended. A connection gets TIME_LIMIT to send its
; request, and again to close; then it is ended (and counted as dropped), or closed outright. VIA T1 keeps the
; time. The network settings are michael_w5500_ping.s's (the home network), so the W5500 answers ping too.
; Interrupts stay off.
  .include base_config_v2.inc

DISPLAY_STRING_PARAM = $00 ; 2 bytes
TO_DECIMAL_PARAM     = $02 ; 10 bytes
W5500_COUNT          = $0C ; 1 byte
W5500_ERRORS         = $0D ; 1 byte
W5500_WORD           = $0E ; 2 bytes
W5500_FAULTS         = $10 ; 2 bytes
VISITS               = $12 ; 2 bytes
POINTER              = $14 ; 2 bytes: send_text's
SENT                 = $16 ; 2 bytes: bytes of the reply put in the TX buffer
TX_START             = $18 ; 2 bytes: where they started
TAKE                 = $1A ; 1 byte: bytes of the request in this read
HEADER_STATE         = $1B ; 1 byte: see scan
LINE_LENGTH          = $1C ; 1 byte: characters of the request's first line kept at LINE_POINTER
LINE_ENDED           = $1D ; 1 byte: non-zero once the first line has ended
LINE_POINTER         = $1E ; 2 bytes: the socket's line, in LINES
SOCKET               = $20 ; 1 byte: the socket being served
REGISTERS            = $21 ; 1 byte: its registers' block (a control byte); its TX buffer's is 8 more, RX 16
STATUS               = $22 ; 1 byte: its Sn_SR
DROPS                = $23 ; 1 byte: connections dropped for sending no request in time

; Each socket's state, indexed by its number
PHASES               = $0200 ; SOCKETS bytes: LISTENING, READING (the request) or CLOSING
TIMERS               = $0208 ; SOCKETS bytes: ticks left in the phase (0: no time left)
HEADERS              = $0210 ; SOCKETS bytes: HEADER_STATE, LINE_LENGTH and LINE_ENDED, kept while another
LENGTHS              = $0218 ; SOCKETS bytes:   socket is served
ENDINGS              = $0220 ; SOCKETS bytes
LINES                = $0300 ; 32 bytes each: the request's first line (LINE_SIZE characters)

SOCKETS              = 4
LISTENING            = 0
READING              = 1
CLOSING              = 2
TICK                 = 50000 ; cycles: 25 ms at 2 MHz
TIME_LIMIT           = 200   ; ticks: 5 s
LINE_SIZE            = 20
PORT                 = 80
CR                   = 13
LF                   = 10

  .org PROGRAM_LOAD_ADDRESS
start:
  jmp initialize_machine

  .include delay_routines.inc
  .include initialize_machine_v2.inc
  .include display_routines.inc
  .include display_decimal.inc
  .include display_hex.inc
  .include fpga_bus.inc
  .include fpga_w5500.inc

program_start:
  ldx #$ff
  txs
  sei
  jsr fb_initialize
  jsr reset_and_enable_display_no_cursor
  stz W5500_FAULTS
  stz W5500_FAULTS + 1
  stz VISITS
  stz VISITS + 1
  stz DROPS
  ldx #(SOCKETS - 1)
.clear:
  stz PHASES,X
  stz TIMERS,X
  dex
  bpl .clear
  lda #<title
  ldx #>title
  jsr display_string
  jsr show_ip
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor

  ldx #W5500_COMMON
  ldy #<W5500_VERSIONR
  jsr w5500_read_register
  bcs .absent
  cmp #W5500_VERSION
  beq .found
.absent:
  lda #<no_w5500
  ldx #>no_w5500
  jsr display_string
.stop:
  bra .stop

.found:
  jsr set_up_network
  jsr start_timer
  jsr show_status
.round:
  lda #0
.next:
  jsr select_socket
  jsr serve
  lda SOCKET
  inc
  cmp #SOCKETS
  bne .next
  jsr count_time
  bra .round


; Serves the selected socket: whatever its state calls for, once
serve:
  ldy #<W5500_SN_SR
  jsr sock_read_register
  sta STATUS
  ldx SOCKET
  cmp #W5500_SOCK_CLOSED
  bne .open
  jmp listen
.open:
  cmp #W5500_SOCK_LISTEN
  beq .done
  cmp #W5500_SOCK_SYNRECV
  beq .done
  cmp #W5500_SOCK_ESTABLISHED
  beq .connected
  cmp #W5500_SOCK_CLOSE_WAIT
  bne .timed                     ; Closing, or anything unexpected
.connected:
  lda PHASES,X
  cmp #CLOSING
  beq .timed                     ; Answered (or given up on): it's closing
  cmp #READING
  beq .reading
  lda #READING                   ; Newly connected: the time for its request starts
  jsr set_phase
.reading:
  jsr take_request
  bcs answer
  lda STATUS
  cmp #W5500_SOCK_CLOSE_WAIT
  beq disconnect                 ; The client has stopped sending, with no request whole
.timed:
  ldx SOCKET
  lda TIMERS,X
  bne .done
  lda PHASES,X
  cmp #READING
  beq .drop
  cmp #CLOSING
  beq .close
  lda #CLOSING                   ; An unexpected state: give it time to close
  jmp set_phase
.drop:                           ; No request in time
  inc DROPS
  jsr show_status
  bra disconnect
.close:                          ; Not closed in time
  lda #W5500_SN_CR_CLOSE
  jmp sock_command
.done:
  rts


; Answers the request with the page, or 404, then ends the connection
answer:
  jsr asks_for_the_page
  bcs .page
  jsr begin_reply
  lda #<not_found
  ldx #>not_found
  jsr send_text
  jsr end_reply
  bra .answered
.page:
  inc VISITS
  bne .counted
  inc VISITS + 1
.counted:
  jsr send_page
.answered:
  jsr show_request
  jsr show_status
  ; fall through

; Ends the connection: the W5500 closes it as the client agrees (serve closes it outright if that takes too long)
disconnect:
  lda #W5500_SN_CR_DISCON
  jsr sock_command
  lda #CLOSING
  ; fall through

; Puts the selected socket in phase A, with TIME_LIMIT for it
set_phase:
  ldx SOCKET
  sta PHASES,X
  lda #TIME_LIMIT
  sta TIMERS,X
  rts


; Selects socket A: SOCKET, REGISTERS and LINE_POINTER
select_socket:
  sta SOCKET
  asl
  asl
  asl
  asl
  asl                            ; 32 times the socket
  sta LINE_POINTER
  ora #W5500_S0_REGISTERS
  sta REGISTERS
  lda #>LINES
  sta LINE_POINTER + 1
  rts


; Starts VIA T1 running free, a tick every TICK cycles (its flag, not an interrupt)
start_timer:
  lda ACR
  and #%00111111
  ora #ACR_T1_CONT
  sta ACR
  lda #<(TICK - 2)
  sta T1CL
  lda #>(TICK - 2)
  sta T1CH
  rts


; If a tick has passed, takes one from each socket's time left
count_time:
  bit IFR
  bvc .done                      ; T1's flag, bit 6
  lda T1CL                       ; Clears it
  ldx #(SOCKETS - 1)
.next:
  lda TIMERS,X
  beq .counted
  dec TIMERS,X
.counted:
  dex
  bpl .next
.done:
  rts


; A software reset, then the network settings
set_up_network:
  ldx #W5500_COMMON
  ldy #<W5500_MR
  lda #W5500_MR_RST
  jsr w5500_write_register
.resetting:
  jsr w5500_read_register
  and #W5500_MR_RST
  bne .resetting
  ldx #>W5500_GAR
  ldy #<W5500_GAR
  lda #W5500_COMMON
  jsr w5500_write
  ldy #0
.setting:
  lda network,Y
  jsr w5500_write_byte
  iny
  cpy #W5500_NETWORK_SIZE
  bne .setting
  jmp w5500_end


; Opens the selected socket for TCP on PORT and listens, ready for a new request
listen:
  ldy #<W5500_SN_MR
  lda #W5500_SN_MR_TCP
  jsr sock_write_register
  lda #<PORT
  sta W5500_WORD
  lda #>PORT
  sta W5500_WORD + 1
  ldy #<W5500_SN_PORT
  jsr sock_write_register16
  lda #W5500_SN_CR_OPEN
  jsr sock_command
  ldy #<W5500_SN_SR
  jsr sock_read_register
  cmp #W5500_SOCK_INIT
  beq .opened
  lda #W5500_SN_CR_CLOSE
  jsr sock_command
  bra listen
.opened:
  ldy #<W5500_SN_IR
  lda #$ff
  jsr sock_write_register        ; Clears every interrupt bit
  lda #W5500_SN_CR_LISTEN
  jsr sock_command
  ldx SOCKET
  stz PHASES,X                   ; LISTENING
  stz TIMERS,X
  stz HEADERS,X
  stz LENGTHS,X
  stz ENDINGS,X
  rts


; Takes what has arrived of the request (255 bytes at most at a time), looking for the blank line that ends its
; headers and keeping its first line's first LINE_SIZE characters at LINE_POINTER.
; On exit carry set once the headers have ended
take_request:
  ldx SOCKET
  lda HEADERS,X
  sta HEADER_STATE
  lda LENGTHS,X
  sta LINE_LENGTH
  lda ENDINGS,X
  sta LINE_ENDED
  ldy #<W5500_SN_RX_RSR
  jsr sock_read_register16
  lda W5500_WORD + 1
  bne .plenty
  lda W5500_WORD
  bne .take
  bra .result                    ; Nothing new
.plenty:
  lda #255
.take:
  sta TAKE
  ldy #<W5500_SN_RX_RD
  jsr sock_read_register16
  lda TAKE
  sta W5500_COUNT
  ldx W5500_WORD + 1
  ldy W5500_WORD
  lda REGISTERS
  clc
  adc #16                        ; The RX buffer
  jsr w5500_read
  ldx TAKE
.next:
  jsr w5500_read_byte
  jsr scan
  dex
  bne .next
  clc
  lda W5500_WORD                 ; Sn_RX_RD, past what was taken
  adc TAKE
  sta W5500_WORD
  bcc .moved
  inc W5500_WORD + 1
.moved:
  ldy #<W5500_SN_RX_RD
  jsr sock_write_register16
  lda #W5500_SN_CR_RECV
  jsr sock_command
  ldx SOCKET
  lda HEADER_STATE
  sta HEADERS,X
  lda LINE_LENGTH
  sta LENGTHS,X
  lda LINE_ENDED
  sta ENDINGS,X
.result:
  lda HEADER_STATE
  cmp #4                         ; Carry set once the headers have ended
  rts


; A byte of the request. HEADER_STATE: 0 in a line, 1 after its CR, 2 at the start of a line, 3 after a CR
; there, 4 the headers have ended (a blank line: CR LF CR LF, or LF LF). X is preserved
scan:
  ldy HEADER_STATE
  cpy #4
  beq .done
  cmp #CR
  beq .cr
  cmp #LF
  beq .lf
  stz HEADER_STATE
  ldy LINE_ENDED
  bne .done
  ldy LINE_LENGTH
  cpy #LINE_SIZE
  beq .done
  sta (LINE_POINTER),Y
  inc LINE_LENGTH
.done:
  rts
.cr:
  lda #1
  cpy #2
  bne .state
  lda #3
  bra .state
.lf:
  lda #2
  cpy #2
  bcc .state                     ; From 0 or 1
  lda #4                         ; From 2 or 3: a blank line
.state:
  sta HEADER_STATE
  sta LINE_ENDED                 ; Non-zero
  rts


; Whether the request's first line asks for the page: GET /, nothing more.
; On exit carry set if it does
asks_for_the_page:
  ldy #0
.compare:
  cpy LINE_LENGTH
  bcs .no                        ; The line is shorter
  lda (LINE_POINTER),Y
  cmp get_root,Y
  bne .no
  iny
  cpy #(get_root_end - get_root)
  bne .compare
  sec
  rts
.no:
  clc
  rts


; The page, with the visitor's number
send_page:
  jsr begin_reply
  lda #<page_head
  ldx #>page_head
  jsr send_text
  lda VISITS
  ldx VISITS + 1
  jsr to_decimal
  jsr send_text
  lda #<page_tail
  ldx #>page_tail
  jsr send_text
  ; fall through

; Ends the reply's frame, moves Sn_TX_WR past it, SENDs it and waits until it has gone
end_reply:
  jsr w5500_end
  clc
  lda TX_START
  adc SENT
  sta W5500_WORD
  lda TX_START + 1
  adc SENT + 1
  sta W5500_WORD + 1
  ldy #<W5500_SN_TX_WR
  jsr sock_write_register16
  lda #W5500_SN_CR_SEND
  jsr sock_command
  ldy #<W5500_SN_IR
.sending:
  jsr sock_read_register
  and #(W5500_SN_IR_SEND_OK | W5500_SN_IR_TIMEOUT)
  beq .sending
  lda #W5500_SN_IR_SEND_OK
  jmp sock_write_register        ; Clears it


; Opens a frame writing the reply into the TX buffer at Sn_TX_WR; send_text streams into it, then end_reply
begin_reply:
  ldy #<W5500_SN_TX_WR
  jsr sock_read_register16
  lda W5500_WORD
  sta TX_START
  lda W5500_WORD + 1
  sta TX_START + 1
  tax
  ldy W5500_WORD
  lda REGISTERS
  clc
  adc #8                         ; The TX buffer
  jsr w5500_write
  stz SENT
  stz SENT + 1
  rts


; Streams a string, NUL-terminated, into the open frame, counting its bytes in SENT.
; On entry A, X = the string's address, low and high bytes
send_text:
  sta POINTER
  stx POINTER + 1
  ldy #0
.next:
  lda (POINTER),Y
  beq .done
  jsr w5500_write_byte
  inc SENT
  bne .counted
  inc SENT + 1
.counted:
  iny
  bne .next
  inc POINTER + 1
  bra .next
.done:
  rts


; Gives the selected socket the command A and waits until the W5500 has taken it (Sn_CR reads 0 again)
sock_command:
  ldy #<W5500_SN_CR
  jsr sock_write_register
.taking:
  jsr sock_read_register
  bne .taking
  rts


; The selected socket's registers: as w5500_read_register and so on, the register at Y
sock_read_register:
  ldx REGISTERS
  jmp w5500_read_register

sock_read_register16:
  ldx REGISTERS
  jmp w5500_read_register16

sock_write_register:
  ldx REGISTERS
  jmp w5500_write_register

sock_write_register16:
  ldx REGISTERS
  jmp w5500_write_register16


; The visits, the faults and the connections dropped
show_status:
  lda #DISPLAY_SECOND_LINE
  jsr move_cursor
  lda #<served
  ldx #>served
  jsr display_string
  lda VISITS
  ldx VISITS + 1
  jsr display_decimal
  lda #DISPLAY_FOURTH_LINE
  jsr move_cursor
  lda #<faults
  ldx #>faults
  jsr display_string
  lda W5500_FAULTS + 1
  jsr display_hex
  lda W5500_FAULTS
  jsr display_hex
  lda #<drop
  ldx #>drop
  jsr display_string
  lda DROPS
  jmp display_hex


; The request's first line, as far as it was kept
show_request:
  lda #DISPLAY_THIRD_LINE
  jsr move_cursor
  ldy #0
.line:
  lda #' '
  cpy LINE_LENGTH
  bcs .show
  lda (LINE_POINTER),Y
.show:
  jsr display_character
  iny
  cpy #LINE_SIZE
  bne .line
  rts


; The IP address, from the settings, in decimal
show_ip:
  ldy #0
.next:
  lda network + W5500_SIPR - W5500_GAR,Y
  ldx #0
  jsr display_decimal
  iny
  cpy #4
  beq .done
  lda #'.'
  jsr display_character
  bra .next
.done:
  rts


; GAR, SUBR, SHAR and SIPR, in the W5500's order
network:
  .byte 192, 168, 86, 1                      ; the gateway: the home router
  .byte 255, 255, 255, 0                     ; the subnet mask
  .byte $02, $65, $02, $00, $00, $01         ; the MAC address (locally administered)
  .byte 192, 168, 86, 251                    ; the IP address

title:    .asciiz "WEB "
no_w5500: .asciiz "NO W5500"
served:   .asciiz "SERVED "
faults:   .asciiz "FAULTS "
drop:     .asciiz " DROP "

get_root:  .byte "GET / "
get_root_end:

not_found:
  .byte "HTTP/1.0 404 Not Found", CR, LF
  .byte "Content-Type: text/plain; charset=us-ascii", CR, LF
  .byte "Connection: close", CR, LF
  .byte CR, LF
  .byte "Not found: Michael has only the one page, at /", LF, 0

; The reply: the HTTP header, then the page, up to the visitor's number; page_tail follows it
page_head:
  .byte "HTTP/1.0 200 OK", CR, LF
  .byte "Content-Type: text/html; charset=us-ascii", CR, LF
  .byte "Connection: close", CR, LF
  .byte "Server: Michael (65C02)", CR, LF
  .byte CR, LF
  .byte "<!DOCTYPE html>", LF
  .byte "<html>", LF
  .byte "<head>", LF
  .byte "<title>Hello from Michael</title>", LF
  .byte "<meta name='viewport' content='width=device-width, initial-scale=1'>", LF
  .byte "<style>", LF
  .byte "body { font-family: Georgia, serif; max-width: 34em; margin: 2em auto; padding: 0 1em;", LF
  .byte "       line-height: 1.6; color: #333; background: #fff8f0; }", LF
  .byte "h1 { color: #b0305a; }", LF
  .byte ".note { background: #fff; border-left: 4px solid #b0305a; padding: 0.5em 1.5em; }", LF
  .byte "footer { color: #888; font-size: 0.85em; margin-top: 2em; }", LF
  .byte "</style>", LF
  .byte "</head>", LF
  .byte "<body>", LF
  .byte "<h1>Hello, world!</h1>", LF
  .byte "<div class='note'>", LF
  .byte "<p>Dear Angel,</p>", LF
  .byte "<p>This little page comes to you from Michael, the 6502 computer on my workbench. An 8-bit", LF
  .byte "processor running at 2 MHz sent every byte of it, one at a time, through an FPGA and a W5500", LF
  .byte "Ethernet chip, out onto our home network and all the way to you.</p>", LF
  .byte "<p>Thank you for your patience with all the wires and the late nights at the workbench.</p>", LF
  .byte "<p>With all my love,<br>Phil</p>", LF
  .byte "</div>", LF
  .byte "<footer>Served by a 65C02 at 2 MHz. You are visitor number ", 0
page_tail:
  .byte ".</footer>", LF
  .byte "</body>", LF
  .byte "</html>", LF, 0
