`timescale 1ns / 1ps
`include "tb_util.vh"
`include "../../rtl/cmod_a7.vh"

// Michael (fpga_bus.inc's timings, with the keyboard driver's interrupt) on one side, the PC on the serial
// port on the other. The board between them is modelled: the VIA's port B, the keyboard board (driving port
// B while SOEB is low) and the data buffer (a 74LVC245 controlled by d_oeb and d_dir). Throughout, no net may
// have two drivers, and the buffer's direction may change only while it is off.
module tb_bus_check;
  localparam real CPU_NS = 500.0;  // one 65C02 cycle at 2 MHz
  localparam CPB = `CLKS_PER_BIT(`PC_BAUD);   // as on the board

  reg clk;
  `TB_CLOCK(clk, 41.667, 200_000_000)  // 12 MHz

  // ---- The board, Michael and the PC -------------------------------------------------------------------
  `include "../../sim/michael_board.vh"
  wire host_tx, fpga_tx;
  wire [1:0] led;

  bus_check #(.SERIAL_DEPTH(256), .ACTIVITY_CYCLES(100)) dut (
    .sysclk(clk), .d(d_pins), .e(e), .rs(rs), .rw(rw), .soeb(soeb), .pa1(1'b1), .pa2(1'b1), .backlight_tie(1'b1),
    .d_oeb(d_oeb), .d_dir(d_dir), .uart_txd_in(host_tx), .uart_rxd_out(fpga_tx),
    .lcd_cs(), .lcd_reset(), .lcd_dc(), .lcd_mosi(), .lcd_sck(), .lcd_led(), .t_clk(), .t_cs(), .t_din(),
    .led(led));

  `include "../../sim/michael_fpga_bus.vh"
  `include "../../sim/host_serial.vh"

  // ---- Michael's side, with counts to compare with the FPGA's ------------------------------------------
  integer writes = 0, reads = 0, pauses = 0, soeb_falls = 0, glitches = 0, commands = 0, short_writes = 0, bounces = 0;
  integer glitches_low = 0, glitches_after_d = 0, glitches_after_rs_rw = 0, glitches_after_d7 = 0,
          glitches_after_many = 0;
  always @(negedge soeb) soeb_falls = soeb_falls + 1;
  task command(input [7:0] b); begin fb_command(b); writes = writes + 1; commands = commands + 1; end endtask
  task data(input [7:0] b);    begin fb_data(b);    writes = writes + 1; end endtask
  reg [7:0] got;
  task expect_read(input [7:0] exp, input irq, input [8*40-1:0] what);
    begin
      fb_read_irq(got, irq); reads = reads + 1; pauses = pauses + irq;
      `CHECK_EQ(got, exp, what)
    end
  endtask
  task expect_status(input [7:0] exp, input [8*40-1:0] what);
    begin fb_status(got); reads = reads + 1; `CHECK_EQ(got, exp, what) end
  endtask

  // ---- Tests ----------------------------------------------------------------------------------------
  integer i;
  initial begin
    #2000;
    `CHECK_EQ({d_oeb, d_dir}, 2'b00, "idle: buffer on, Michael to the FPGA")
    `CHECK_EQ(fpga_drives, 1'b0, "idle: the FPGA doesn't drive the D pins")

    // ID, and a clean status
    command(8'h03);
    command(8'h01);
    expect_read("M", 0, "ID byte 1");
    expect_read("B", 0, "ID byte 2");
    expect_read(8'd1, 0, "ID: protocol version");
    expect_read(8'h00, 0, "ID: capabilities");
    expect_status(8'h00, "status after ID");

    // ECHO: every byte value written comes back in order
    command(8'h04);
    for (i = 0; i < 256; i = i + 1) data(i);
    for (i = 0; i < 256; i = i + 1) expect_read(i, 0, "ECHO byte read back");
    expect_status(8'h00, "status after ECHO");

    // An empty reply queue reads $00 and sets UNDERFLOW, which a status read reports once
    expect_read(8'h00, 0, "read with the reply queue empty");
    expect_status(8'h08, "UNDERFLOW");
    expect_status(8'h00, "UNDERFLOW cleared by reading the status");

    // Unknown commands, and data after a command that doesn't stream
    command(8'h7F); data(8'h11);
    expect_status(8'h02, "UNKNOWN (its data ignored)");
    command(8'h00); data(8'h22);
    expect_status(8'h04, "EXTRA");

    // A keyboard interrupt in the middle of a read: the keyboard board gets port B to itself, the FPGA
    // drives it again afterwards, and Michael reads the right byte
    command(8'h04); data(8'hA5); data(8'h5A);
    kbd_byte = 8'h3C;
    expect_read(8'hA5, 1, "byte read across a keyboard interrupt");
    `CHECK_EQ(kbd_got, 8'h3C, "the keyboard interrupt read the keyboard board's byte");
    expect_read(8'h5A, 0, "the next byte after the interrupted read");

    // ... and in the middle of a write: the FPGA took the byte as E rose
    kbd_byte = 8'hC3;
    fb_data_irq(8'h96, 1'b1); writes = writes + 1;
    `CHECK_EQ(kbd_got, 8'hC3, "the keyboard interrupt during a write read the keyboard board's byte");
    expect_read(8'h96, 0, "byte written across a keyboard interrupt");
    expect_status(8'h00, "status after the interrupted transfers");

    // OVERFLOW: one byte more than the reply queue holds; RESET empties it
    for (i = 0; i < 513; i = i + 1) data(i);
    expect_status(8'h10, "OVERFLOW");
    expect_read(8'h00, 0, "the queue keeps the first bytes");
    command(8'h03);
    expect_read(8'h00, 0, "RESET empties the reply queue");
    expect_status(8'h08, "a read after RESET underflows");

    // Glitches on E shorter than the filter (3 samples, 250 ns) are ignored, and counted: one while idle
    // (with RW high, as after a read), one in the middle of a read
    rw = 1'b1; #2000; e = 1'b1; #120; e = 1'b0; #2000; rw = 1'b0; glitches = glitches + 1;
    glitches_low = glitches_low + 1;
    command(8'h04); data(8'h44); data(8'h55);
    fork
      expect_read(8'h44, 0, "a read with a glitch while E is high");
      begin wait (e); #1500; e = 1'b0; #120; e = 1'b1; glitches = glitches + 1; end
    join
    expect_read(8'h55, 0, "the glitch didn't end the read or take a byte");
    expect_status(8'h00, "status after the glitches");

    // Glitches just after port B or RS changes, with E low (as crosstalk from a neighbouring wire would make)
    via_drive = 1'b1; via_out = 8'h00; #2000; via_out = 8'hF0; #100; e = 1'b1; #90; e = 1'b0; #2000;
    rs = 1'b1; #100; e = 1'b1; #90; e = 1'b0; #2000; rs = 1'b0; #2000;
    glitches = glitches + 2; glitches_low = glitches_low + 2;
    glitches_after_d = glitches_after_d + 1; glitches_after_rs_rw = glitches_after_rs_rw + 1;
    glitches_after_d7 = glitches_after_d7 + 1; glitches_after_many = glitches_after_many + 1;   // $00 to $F0

    // A flicker at an edge (E rising, back low for a sample, then high for good) is a bounce, not a glitch,
    // and the write it starts still happens once
    command(8'h04);
    rs = 1'b1; #2000; via_drive = 1'b1; via_out = 8'h77; #2000;
    e = 1'b1; #90; e = 1'b0; #90; e = 1'b1; #3000; e = 1'b0; #2000; rs = 1'b0;
    writes = writes + 1; bounces = bounces + 1;
    expect_read(8'h77, 0, "the byte written across a bounce");

    // A write whose E pulse is shorter than any Michael makes (1 us; Michael's are 3 us or more) is counted
    // as a write and as a short one
    command(8'h04);
    rs = 1'b1; #2000; via_drive = 1'b1; via_out = 8'h66; #2000; e = 1'b1; #1000; e = 1'b0; #2000; rs = 1'b0;
    writes = writes + 1; short_writes = short_writes + 1;
    expect_read(8'h66, 0, "the short write's byte");

    // '1' from the PC holds the data buffer off while the bus is idle (for experiments on switching noise);
    // '0' puts it back
    send_host("1");
    #200000; `CHECK_EQ(d_oeb, 1'b1, "data buffer held off while idle after '1'")
    send_host("0");
    #200000; `CHECK_EQ(d_oeb, 1'b0, "data buffer back on after '0'")

    // SERIAL_SEND reaches the PC; '?' adds the counts
    command(8'h50); data("O"); data("K"); data(8'h0D); data(8'h0A);
    expect_status(8'h80, "BUSY while the serial output is still going");
    expect_line({"OK"}, "SERIAL_SEND line");
    #20000;
    expect_status(8'h00, "BUSY clear once it has gone");
    `CHECK_EQ(led[1], 1'b1, "LD2 lit once a read was paused")
    send_host("?");
    expect_line({"C ", hex4(writes), " ", hex4(reads), " ", hex4(pauses), " ", hex4(soeb_falls), " ", hex4(glitches),
                 " ", hex4(commands), " ", hex4(short_writes), " ", hex4(bounces), " ", hex4(glitches_low), " ",
                 hex4(glitches_after_d), " ", hex4(glitches_after_rs_rw), " ", hex4(glitches_after_d7), " ",
                 hex4(glitches_after_many)}, "counts line");
    `TB_PASS
  end

  function [7:0] hex(input [3:0] n); hex = n < 10 ? "0" + n : "A" + n - 10; endfunction
  function [31:0] hex4(input [15:0] v); hex4 = {hex(v[15:12]), hex(v[11:8]), hex(v[7:4]), hex(v[3:0])}; endfunction
endmodule
