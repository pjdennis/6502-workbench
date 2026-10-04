// Michael using the FPGA bus as firmware/lib/fpga/fpga_bus.inc does, with that code's cycle timings at 2 MHz,
// and the keyboard driver's interrupt (firmware/lib/keyboard/keyboard_driver.inc), which can arrive in the
// middle of a transfer. Include inside a testbench module that declares `reg e, rs, rw, soeb, via_drive`,
// `reg [7:0] via_out, kbd_byte`, `wire [7:0] portb` (Michael's port B), `localparam real CPU_NS` and
// `realtime t_e_rise, t_e_fall`.
  task cycles(input integer n); #(n * CPU_NS); endtask

  task set_e(input v);
    begin e = v; if (v) t_e_rise = $realtime; else t_e_fall = $realtime; end
  endtask

  // The keyboard driver's interrupt, as it reads a byte from the keyboard board: it saves the ports, makes
  // port B an input and PA5/PA6 (RS, RW) inputs, which the keyboard board then drives, enables the board's
  // shift register (SOEB low), reads port B, and restores everything.
  reg [7:0] kbd_got;
  task keyboard_interrupt;
    reg rs_was, rw_was, drive_was;
    begin
      rs_was = rs; rw_was = rw; drive_was = via_drive;
      cycles(7 + 3 + 6 + 2 + 4 + 3 + 4 + 3 + 2 + 2 + 4 + 3);   // entry, checks, PCR, KEYBOARD_RECEIVING
      cycles(4 + 3 + 4 + 3 + 4 + 3 + 4 + 3);                   // save PORTA, DDRA, PORTB, DDRB
      cycles(2 + 4); via_drive = 1'b0;                         // stz DDRB (as lda/sta)
      cycles(2 + 6); rs = 1'bx; rw = 1'bx;                     // trb DDRA: ACK and PARITY inputs
      cycles(2 + 6); soeb = 1'b0;                              // trb PORTA: SOEB low
      cycles(3 + 3 + 4); kbd_got = portb;                      // lda PORTB
      cycles(2 + 2 + 2 + 30 + 3);                              // eor, cmp, KB_BUFFER_WRITE
      cycles(2 + 6); soeb = 1'b1;                              // tsb PORTA: SOEB high
      cycles(4 + 4); via_drive = drive_was;                    // restore DDRB
      cycles(4 + 4 + 4 + 4); rs = rs_was; rw = rw_was;         // restore PORTB, DDRA
      cycles(4 + 4 + 3 + 6 + 4 + 6);                           // restore PORTA, return, rti
    end
  endtask

  // fb_write's common part: sta DDRB, sta PORTB, E up and down (with an interrupt while E is high, if asked)
  task fb_write(input [7:0] b, input irq);
    begin
      cycles(2 + 4); via_drive = 1'b1;
      cycles(4 + 4); via_out = b;
      cycles(3 + 2 + 6); set_e(1'b1);
      if (irq) keyboard_interrupt;
      cycles(6); set_e(1'b0);
      cycles(2 + 6); rs = 1'b0;
      cycles(4 + 6);
    end
  endtask

  task fb_command(input [7:0] b);
    begin cycles(6 + 3 + 2 + 6); rs = 1'b0; rw = 1'b0; cycles(3); fb_write(b, 1'b0); end
  endtask

  task fb_data_irq(input [7:0] b, input irq);
    begin cycles(6 + 3 + 2 + 6); rw = 1'b0; cycles(2 + 6); rs = 1'b1; fb_write(b, irq); end
  endtask

  task fb_data(input [7:0] b); fb_data_irq(b, 1'b0); endtask

  // fb_read_byte: stz DDRB, RW high, E up, ldx PORTB (with an interrupt first, if asked), E down, RW low
  task fb_read_byte(output [7:0] b, input irq);
    begin
      cycles(4); via_drive = 1'b0;
      cycles(2 + 6); rw = 1'b1;
      cycles(2 + 6); set_e(1'b1);
      if (irq) keyboard_interrupt;
      cycles(4); b = portb;
      cycles(6); set_e(1'b0);
      cycles(2 + 6); rs = 1'b0; rw = 1'b0;
      cycles(2 + 4 + 2 + 6);                                   // txa, plx, cmp #0, rts
    end
  endtask

  task fb_read_irq(output [7:0] b, input irq);
    begin cycles(6 + 3 + 2 + 6); rs = 1'b1; cycles(3); fb_read_byte(b, irq); end
  endtask

  task fb_read(output [7:0] b); fb_read_irq(b, 1'b0); endtask

  task fb_status(output [7:0] b);
    begin cycles(6 + 3 + 2 + 6); rs = 1'b0; fb_read_byte(b, 1'b0); end
  endtask
