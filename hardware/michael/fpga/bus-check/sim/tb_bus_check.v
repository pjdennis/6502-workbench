`timescale 1ns / 1ps
`include "tb_util.vh"

// Michael (fpga_bus.inc's timings, with the keyboard driver's interrupt) on one side, the PC on the serial
// port on the other. The board between them is modelled: the VIA's port B, the keyboard board (driving port
// B while SOEB is low) and the data buffer (a 74LVC245 controlled by d_oeb and d_dir). Throughout, no net may
// have two drivers, and the buffer's direction may change only while it is off.
module tb_bus_check;
  localparam real CPU_NS = 500.0;  // one 65C02 cycle at 2 MHz
  localparam CPB = 104;            // 115200 baud, as on the board

  reg clk;
  `TB_CLOCK(clk, 41.667, 200_000_000)  // 12 MHz

  // ---- The board ------------------------------------------------------------------------------------
  reg        e = 1'b0, rs = 1'b0, rw = 1'b0, soeb = 1'b1, via_drive = 1'b0;
  reg  [7:0] via_out = 8'h00, kbd_byte = 8'h00;
  wire [7:0] portb, d_pins;
  wire       d_oeb, d_dir;
  wire       buf_to_michael = !d_oeb && d_dir, buf_to_fpga = !d_oeb && !d_dir;

  assign portb  = via_drive      ? via_out  : 8'bz;
  assign portb  = !soeb          ? kbd_byte : 8'bz;
  assign portb  = buf_to_michael ? d_pins   : 8'bz;
  assign d_pins = buf_to_fpga    ? portb    : 8'bz;

  wire host_tx, fpga_tx, host_ready, rx_valid;
  wire [7:0] rx_data;
  reg  host_valid = 1'b0;
  reg  [7:0] host_data = 8'h00;
  wire [1:0] led;

  bus_check #(.CLKS_PER_BIT(CPB), .SERIAL_DEPTH(256), .ACTIVITY_CYCLES(100)) dut (
    .sysclk(clk), .d(d_pins), .e(e), .rs(rs), .rw(rw), .soeb(soeb), .csb(1'b1), .rstb(1'b1), .bl(1'b1),
    .d_oeb(d_oeb), .d_dir(d_dir), .uart_txd_in(host_tx), .uart_rxd_out(fpga_tx),
    .lcd_cs(), .lcd_reset(), .lcd_dc(), .lcd_mosi(), .lcd_sck(), .lcd_led(), .t_clk(), .t_cs(), .t_din(),
    .led(led));

  // No two drivers on a net. Checked 1 ns after any change: the parts switch in zero time here, and the
  // real ones take a few ns.
  wire fpga_drives = dut.d_drive;
  always @(via_drive, soeb, buf_to_michael, buf_to_fpga, fpga_drives) #1 begin
    `CHECK(via_drive + !soeb + buf_to_michael <= 1, "two drivers on port B")
    `CHECK(buf_to_fpga + fpga_drives <= 1, "two drivers on the D pins")
  end
  always @(d_dir) if ($time > 0) `CHECK_EQ(d_oeb, 1'b1, "DIR changed while the buffer was on")

  // Reads: the byte reaches port B within 1 us of E rising, and the bus is released within 1 us of E
  // falling (unless the keyboard board took port B first)
  realtime t_e_rise = 0, t_e_fall = 0, t_drive = 0;
  always @(posedge buf_to_michael) begin   // the read's first drive: later ones follow a keyboard interrupt
    if (t_drive < t_e_rise) `CHECK($realtime - t_e_rise <= 1000.0, "byte on port B more than 1 us after E rose")
    t_drive = $realtime;
  end
  always @(negedge buf_to_michael) if (!e)
    `CHECK($realtime - t_e_fall <= 1000.0, "port B released more than 1 us after E fell")

  `include "../../sim/michael_fpga_bus.vh"

  // ---- The PC ---------------------------------------------------------------------------------------
  uart_tx #(.CLKS_PER_BIT(CPB)) host_uart_tx (.clk(clk), .valid(host_valid), .data(host_data), .ready(host_ready), .tx(host_tx));
  uart_rx #(.CLKS_PER_BIT(CPB)) host_uart_rx (.clk(clk), .rx(fpga_tx), .valid(rx_valid), .data(rx_data));

  reg [8*64-1:0] line = 0;   // the latest complete line received, without CR LF
  reg [8*64-1:0] partial = 0;
  integer n_lines = 0;
  always @(posedge clk) if (rx_valid) begin
    if (rx_data == 8'h0A) begin line = partial; partial = 0; n_lines = n_lines + 1; end
    else if (rx_data != 8'h0D) partial = {partial[8*63-1:0], rx_data};
  end

  task send_host(input [7:0] b);
    begin
      host_data = b; host_valid = 1;
      @(posedge clk); while (!host_ready) @(posedge clk);
      #1 host_valid = 0;
    end
  endtask

  task expect_line(input [8*64-1:0] exp, input [8*40-1:0] what);
    integer lines_before, waited;
    begin
      lines_before = n_lines;
      for (waited = 0; n_lines == lines_before && waited < 5000; waited = waited + 1) #1000;
      if (line !== exp) $display("got \"%0s\", expected \"%0s\"", line, exp);
      `CHECK(line === exp, what)
    end
  endtask

  // ---- Michael's side, with counts to compare with the FPGA's ------------------------------------------
  integer writes = 0, reads = 0, pauses = 0, soeb_falls = 0, glitches = 0;
  always @(negedge soeb) soeb_falls = soeb_falls + 1;
  task command(input [7:0] b); begin fb_command(b); writes = writes + 1; end endtask
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
    command(8'h04); data(8'h44); data(8'h55);
    fork
      expect_read(8'h44, 0, "a read with a glitch while E is high");
      begin wait (e); #1500; e = 1'b0; #120; e = 1'b1; glitches = glitches + 1; end
    join
    expect_read(8'h55, 0, "the glitch didn't end the read or take a byte");
    expect_status(8'h00, "status after the glitches");

    // SERIAL_SEND reaches the PC; '?' adds the counts
    command(8'h50); data("O"); data("K"); data(8'h0D); data(8'h0A);
    expect_status(8'h80, "BUSY while the serial output is still going");
    expect_line({"OK"}, "SERIAL_SEND line");
    #20000;
    expect_status(8'h00, "BUSY clear once it has gone");
    `CHECK_EQ(led[1], 1'b1, "LD2 lit once a read was paused")
    send_host("?");
    expect_line({"C ", hex4(writes), " ", hex4(reads), " ", hex4(pauses), " ", hex4(soeb_falls), " ", hex4(glitches)},
                "counts line");
    `TB_PASS
  end

  function [7:0] hex(input [3:0] n); hex = n < 10 ? "0" + n : "A" + n - 10; endfunction
  function [31:0] hex4(input [15:0] v); hex4 = {hex(v[15:12]), hex(v[11:8]), hex(v[7:4]), hex(v[3:0])}; endfunction
endmodule
