`timescale 1ns / 1ps
`include "tb_util.vh"

// Michael (the shared VIA model) drives the inputs; the host side decodes the FPGA's serial report and
// checks it line by line. Report lines are 12 characters:
//   "S dd ecrdb\r\n"  inputs settled: port B in hex, then E, CSB, RSTB, DC, backlight
//   "B dd ecrdb\r\n"  a byte the SPI bridge latched, with the control levels at that moment
//   "! OVERFLOW\r\n"  the event buffer filled and events were lost
module tb_input_check;
  localparam real CPU_NS = 500.0;
  localparam SETTLE = 120, CPB = 4, LEN = 12;  // 10 us settle time and 3 Mbaud keep the simulation short
  localparam real SETTLE_NS = SETTLE * 83.333;

  reg clk;
  reg [7:0] portb = 8'h00;
  reg e = 1'b0, csb = 1'b1, rstb = 1'b1, dc = 1'b0, bl = 1'b1;
  reg host_valid = 1'b0;
  reg [7:0] host_data = 0;
  wire host_ready, host_tx, fpga_tx, small_tx;

  input_check #(.SETTLE_CYCLES(SETTLE), .CLKS_PER_BIT(CPB), .FIFO_DEPTH(512)) dut (
    .sysclk(clk), .d(portb), .e(e), .csb(csb), .rstb(rstb), .dc(dc), .bl(bl),
    .uart_txd_in(host_tx), .uart_rxd_out(fpga_tx),
    .lcd_cs(), .lcd_reset(), .lcd_dc(), .lcd_mosi(), .lcd_sck(), .lcd_led(), .t_clk(), .t_cs(), .t_din(), .led());
  // A copy with a tiny buffer, to check that overflow is reported
  input_check #(.SETTLE_CYCLES(SETTLE), .CLKS_PER_BIT(CPB), .FIFO_DEPTH(8)) dut_small (
    .sysclk(clk), .d(portb), .e(e), .csb(csb), .rstb(rstb), .dc(dc), .bl(bl),
    .uart_txd_in(1'b1), .uart_rxd_out(small_tx),
    .lcd_cs(), .lcd_reset(), .lcd_dc(), .lcd_mosi(), .lcd_sck(), .lcd_led(), .t_clk(), .t_cs(), .t_din(), .led());

  uart_tx #(.CLKS_PER_BIT(CPB)) host_uart_tx (.clk(clk), .valid(host_valid), .data(host_data), .ready(host_ready), .tx(host_tx));

  `TB_CLOCK(clk, 41.667, 20_000_000)

  // ---- Expected report ------------------------------------------------------------------------------
  reg [8*LEN-1:0] exp_line [0:2047];
  integer n_exp = 0;
  reg [12:0] last_settled = 13'h1FFF;  // nothing reported yet

  function [7:0] hex(input [3:0] n); hex = n < 10 ? "0" + n : "A" + n - 10; endfunction
  function [8*LEN-1:0] report(input [7:0] kind, input [7:0] dd, input [4:0] ctrl);
    integer i;
    begin
      report = {kind, " ", hex(dd[7:4]), hex(dd[3:0]), " ", 40'h0, 8'h0D, 8'h0A};
      for (i = 0; i < 5; i = i + 1) report[8*(6-i) +: 8] = "0" + ctrl[4-i];
    end
  endfunction
  task push(input [8*LEN-1:0] line); begin exp_line[n_exp] = line; n_exp = n_exp + 1; end endtask

  // Called by the Michael model as a byte's E strobe rises with the display selected
  task expect_byte(input [7:0] b, input d); push(report("B", b, {1'b1, 1'b0, 1'b1, d, bl})); endtask

  // Hold the inputs long enough to settle; the FPGA reports the state if it differs from the last one
  task settled;
    reg [12:0] now;
    begin
      #(SETTLE_NS * 1.5);
      now = {portb, e, csb, rstb, dc, bl};
      if (now != last_settled) push(report("S", portb, {e, csb, rstb, dc, bl}));
      last_settled = now;
      #(SETTLE_NS * 0.5);
    end
  endtask

  task query;
    begin
      push(report("S", portb, {e, csb, rstb, dc, bl}));
      host_data = "?"; host_valid = 1; @(posedge clk); while (!host_ready) @(posedge clk); #1 host_valid = 0;
      #(20 * CPB * 83.333);
    end
  endtask

  `include "../sim/michael_via.vh"

  // ---- Host: decode the report and compare ----------------------------------------------------------
  wire rx_valid, small_valid;
  wire [7:0] rx_data, small_data;
  uart_rx #(.CLKS_PER_BIT(CPB)) host_uart_rx (.clk(clk), .rx(fpga_tx), .valid(rx_valid), .data(rx_data));
  uart_rx #(.CLKS_PER_BIT(CPB)) small_uart_rx (.clk(clk), .rx(small_tx), .valid(small_valid), .data(small_data));

  reg [8*LEN-1:0] got = 0, small_got = 0;
  integer n_got = 0, n_chars = 0;
  reg small_overflowed = 1'b0;
  always @(posedge clk) begin
    if (rx_valid) begin
      got = {got[8*LEN-9:0], rx_data};
      n_chars = n_chars + 1;
      if (rx_data == 8'h0A) begin
        `CHECK_EQ(n_chars, LEN, "report line length")
        `CHECK(n_got < n_exp, "FPGA reported an event that shouldn't have happened")
        if (got !== exp_line[n_got]) begin
          $display("line %0d: got \"%s\", expected \"%s\"", n_got, got[8*LEN-1:16], exp_line[n_got][8*LEN-1:16]);
          `CHECK(0, "report line")
        end
        n_got = n_got + 1;
        n_chars = 0;
      end
    end
    if (small_valid) begin
      small_got = {small_got[8*LEN-9:0], small_data};
      if (small_got == {"! OVERFLOW", 8'h0D, 8'h0A}) small_overflowed = 1'b1;
    end
  end

  // Waits for the FIFO to drain (up to a line time per expected line), then a little longer for extras
  task expect_all_reported;
    integer waited;
    begin
      for (waited = 0; n_got < n_exp && waited < n_exp + 10; waited = waited + 1) #(10 * CPB * 83.333 * LEN);
      #(3 * 10 * CPB * 83.333 * LEN);
      `CHECK_EQ(n_got, n_exp, "report lines received")
    end
  endtask

  // ---- Tests ----------------------------------------------------------------------------------------
  integer i;
  initial begin
    settled;   // the first settled state is reported at start-up
    query;     // '?' reports the current state even when nothing changed
    expect_all_reported;

    // One line at a time, as the Michael test program does
    for (i = 0; i < 8; i = i + 1) begin portb = 8'h01 << i; settled; end
    portb = 8'h00; settled;
    portb = 8'h5A; #(SETTLE_NS * 0.3); portb = 8'h00; settled;  // a brief glitch is not a settled state
    e = 1; settled; e = 0; settled;
    csb = 0; settled; csb = 1; settled;
    rstb = 0; settled; rstb = 1; settled;
    dc = 1; settled; dc = 0; settled;
    bl = 0; settled; bl = 1; settled;
    expect_all_reported;

    // Bytes through the driver's routines, at the fill loop's full speed too
    gd_configure; gd_select; settled;
    gd_send_command(8'h2A);
    for (i = 0; i < 16; i = i + 1) gd_send_data(i * 17);
    gd_send_command(8'h2C);
    fast_fill(8'h00, 64);
    portb = 8'h00; settled;          // back where it was: no new state line
    gd_unselect; settled;
    expect_all_reported;
    `CHECK_EQ(small_overflowed, 1'b1, "overflow reported when the buffer fills")
    `TB_PASS
  end
endmodule
