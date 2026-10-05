`timescale 1ns / 1ps
`include "../../rtl/cmod_a7.vh"
// Bring-up check for the Michael FPGA bus's reads (stage 1 of docs/michael-fpga-bus-plan.md): the bus
// (michael_bus.v) with its control commands (bus_control.v): NOP, ID, RESET, ECHO, the status read, and
// SERIAL_SEND ($50, provisional), whose bytes go out of the Cmod's USB serial port (115200 8N1). Michael's
// test program reports its results that way.
//
// '1' from the PC holds the data buffer off while the bus is idle, and '0' puts it back: for telling switching
// noise from the buffer's outputs from noise upstream of it. E still arrives (through the control buffer), so
// a write still counts, but with whatever the undriven D pins read.
// SERIAL_SEND's bytes beyond the serial queue's 2048 are dropped, unreported (the check's reports are short).
// '?' from the PC adds a line of counts to the serial output, once it's idle:
//   "C wwww rrrr pppp ssss gggg cccc tttt bbbb"  in hex: transfers written, bytes read (replies and status),
//       reads paused by the SOEB interlock, SOEB's falls at any time (each keyboard byte Michael reads),
//       glitches on E (changes shorter than the bus's filter, so ignored, in the middle of a steady level), the
//       writes that were commands, writes whose E pulse was shorter than SHORT_E (Michael's strobes last 3 us
//       or more), bounces (such changes within NEAR_EDGE samples of a real edge of E), and of the glitches:
//       those while E was low, those within NEAR_EDGE samples after a change on D, those within NEAR_EDGE
//       samples after a change of RS or RW, those after a change of D7 (beside E on the Cmod), and those after
//       changes of 4 or more bits of D
// The display is held idle. LD1 flashes on bus traffic; LD2 lights once a read has been paused.
module bus_check #(
  parameter BAUD            = `PC_BAUD,
  parameter SERIAL_DEPTH    = 2048,
  parameter ACTIVITY_CYCLES = 600_000,  // 50 ms at 12 MHz
  parameter SHORT_E         = 18,       // 1.5 us at 12 MHz
  parameter NEAR_EDGE       = 6         // 0.5 us
) (
  input        sysclk,
  inout  [7:0] d,
  input        e,
  input        rs,
  input        rw,
  input        soeb,
  input        pio9,         // unused: ties (stage 4 moved E to Cmod 11), and the backlight tie
  input        pio10,
  input        backlight_tie,
  output       d_oeb,
  output       d_dir,
  input        uart_txd_in,
  output       uart_rxd_out,
  output       lcd_cs,
  output       lcd_reset,
  output       lcd_dc,
  output       lcd_mosi,
  output       lcd_sck,
  output       lcd_led,
  output       t_clk,
  output       t_cs,
  output       t_din,
  output [1:0] led
);
  localparam CLKS_PER_BIT = `CLKS_PER_BIT(BAUD);
  localparam LINE = 68;

  assign {lcd_cs, lcd_reset, lcd_dc, lcd_mosi, lcd_sck, lcd_led} = 6'b110000;
  assign {t_cs, t_clk, t_din} = 3'b100;

  // The bus
  wire [7:0] d_out, wr_data, reply_byte, status_byte, ser_data;
  wire       d_drive, wr, wr_rs, rd, rd_end, rd_rs, paused, glitch, e_filtered, ser_valid;
  reg        hold_off = 1'b0;   // set by '1' from the PC
  assign d = d_drive ? d_out : 8'bz;

  michael_bus bus (
    .clk(sysclk), .d_in(d), .d_out(d_out), .d_drive(d_drive), .e(e), .rs(rs), .rw(rw), .soeb(soeb), .hold_off(hold_off),
    .d_oeb(d_oeb), .d_dir(d_dir), .wr(wr), .wr_rs(wr_rs), .wr_data(wr_data), .rd(rd), .rd_end(rd_end),
    .rd_rs(rd_rs), .reply_byte(reply_byte), .status_byte(status_byte), .paused(paused), .glitch(glitch),
    .e_filtered(e_filtered));

  wire serial_busy;
  bus_control control (
    .clk(sysclk), .wr(wr), .wr_rs(wr_rs), .wr_data(wr_data), .rd(rd), .rd_end(rd_end), .rd_rs(rd_rs),
    .reply_byte(reply_byte), .status_byte(status_byte), .busy(serial_busy),
    .ser_valid(ser_valid), .ser_data(ser_data), .disp_push(), .disp_kind(), .disp_value(), .disp_full(1'b0),
    .text_push(), .text_op(), .text_a(), .text_b(), .text_full(1'b0));

  // Counts
  reg [15:0] writes = 0, reads = 0, pauses = 0, soeb_falls = 0, glitches = 0, commands = 0, short_writes = 0,
             bounces = 0, glitches_low = 0, glitches_after_d = 0, glitches_after_rs_rw = 0, glitches_after_d7 = 0,
             glitches_after_many = 0;
  reg  [7:0] d_changed = 0;   // the bits of D that changed within NEAR_EDGE samples
  reg        glitch_after_d7 = 1'b0, glitch_after_many = 1'b0;
  function [3:0] ones(input [7:0] v); ones = v[0] + v[1] + v[2] + v[3] + v[4] + v[5] + v[6] + v[7]; endfunction
  // D, RS and RW, synchronised, and how long since each last changed (up to NEAR_EDGE samples)
  reg  [9:0] lines1 = 0, lines2 = 0, lines_was = 0;
  reg [$clog2(NEAR_EDGE+1)-1:0] since_d = NEAR_EDGE, since_rs_rw = NEAR_EDGE;
  reg        glitch_low = 1'b0, glitch_after_d = 1'b0, glitch_after_rs_rw = 1'b0;   // as the glitch began
  reg [$clog2(NEAR_EDGE+1)-1:0] since_edge = NEAR_EDGE, deciding = 0;   // samples since E's last edge; a
                                                                        // glitch waiting to see if an edge follows
  reg [$clog2(SHORT_E)-1:0] e_high = 0;   // how long E has been high, up to SHORT_E
  reg        writing = 1'b0, e_was = 1'b0;
  reg        paused_ever = 1'b0;
  reg  [2:0] soeb_sync = 3'b111;
  always @(posedge sysclk) begin
    soeb_sync <= {soeb_sync[1:0], soeb};
    if (wr)     writes <= writes + 1'b1;
    if (rd)     reads  <= reads + 1'b1;
    if (paused) begin pauses <= pauses + 1'b1; paused_ever <= 1'b1; end
    if (soeb_sync[2:1] == 2'b10) soeb_falls <= soeb_falls + 1'b1;
    lines1 <= {d, rs, rw}; lines2 <= lines1; lines_was <= lines2;
    if (lines2[9:2] != lines_was[9:2]) begin
      since_d   <= 0;
      d_changed <= (since_d != NEAR_EDGE ? d_changed : 8'h00) | (lines2[9:2] ^ lines_was[9:2]);
    end else if (since_d != NEAR_EDGE) since_d <= since_d + 1'b1;
    if (lines2[1:0] != lines_was[1:0]) since_rs_rw <= 0;
    else if (since_rs_rw != NEAR_EDGE)  since_rs_rw <= since_rs_rw + 1'b1;
    if (e_was != e_filtered)       since_edge <= 0;
    else if (since_edge != NEAR_EDGE) since_edge <= since_edge + 1'b1;
    if (glitch) begin
      if (since_edge != NEAR_EDGE) bounces <= bounces + 1'b1;   // just after an edge
      else begin                                              // an edge just after makes it a bounce too
        deciding           <= NEAR_EDGE;
        glitch_low         <= !e_filtered;
        glitch_after_d     <= since_d != NEAR_EDGE;
        glitch_after_rs_rw <= since_rs_rw != NEAR_EDGE;
        glitch_after_d7    <= since_d != NEAR_EDGE && d_changed[7];
        glitch_after_many  <= since_d != NEAR_EDGE && ones(d_changed) >= 4;
      end
    end else if (deciding != 0) begin
      if (e_was != e_filtered) begin bounces <= bounces + 1'b1; deciding <= 0; end
      else begin
        if (deciding == 1) begin
          glitches             <= glitches + 1'b1;
          glitches_low         <= glitches_low + glitch_low;
          glitches_after_d     <= glitches_after_d + glitch_after_d;
          glitches_after_rs_rw <= glitches_after_rs_rw + glitch_after_rs_rw;
          glitches_after_d7    <= glitches_after_d7 + glitch_after_d7;
          glitches_after_many  <= glitches_after_many + glitch_after_many;
        end
        deciding <= deciding - 1'b1;
      end
    end
    if (wr && !wr_rs) commands <= commands + 1'b1;
    e_was <= e_filtered;
    if (!e_filtered) e_high <= 0;
    else if (e_high != SHORT_E) e_high <= e_high + 1'b1;
    if (wr) writing <= 1'b1;
    if (e_was && !e_filtered) begin
      if (writing && e_high != SHORT_E) short_writes <= short_writes + 1'b1;
      writing <= 1'b0;
    end
  end

  reg [$clog2(ACTIVITY_CYCLES)-1:0] activity = 0;
  always @(posedge sysclk)
    if (wr || rd)           activity <= ACTIVITY_CYCLES - 1;
    else if (activity != 0) activity <= activity - 1'b1;
  assign led = {paused_ever, activity != 0};

  // '?' from the PC: a line of counts, queued when the serial output has nothing else to send
  wire       rx_valid;
  wire [7:0] rx_data;
  uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_rx (.clk(sysclk), .rx(uart_txd_in), .valid(rx_valid), .data(rx_data));

  function [7:0] hex(input [3:0] n); hex = n < 10 ? "0" + n : "A" + n - 10; endfunction
  function [31:0] hex4(input [15:0] v); hex4 = {hex(v[15:12]), hex(v[11:8]), hex(v[7:4]), hex(v[3:0])}; endfunction

  always @(posedge sysclk)
    if (rx_valid && rx_data == "1")      hold_off <= 1'b1;
    else if (rx_valid && rx_data == "0") hold_off <= 1'b0;

  reg              query_waiting = 1'b0;
  reg [8*LINE-1:0] query_line = 0;
  reg [6:0]        query_left = 0;
  wire             query_push = query_left != 0 && !ser_valid;

  // Serial output queue, drained into the UART
  wire [7:0] tx_data;
  wire       tx_ready, serial_empty;
  fifo #(.WIDTH(8), .DEPTH(SERIAL_DEPTH)) serial_out (
    .clk(sysclk), .clear(1'b0), .push(ser_valid || query_push),
    .din(ser_valid ? ser_data : query_line[8*LINE-1 -: 8]), .full(), .pop(!serial_empty && tx_ready),
    .dout(tx_data), .empty(serial_empty), .count());
  assign serial_busy = !serial_empty || !tx_ready;

  always @(posedge sysclk) begin
    if (rx_valid && rx_data == "?") query_waiting <= 1'b1;
    if (query_waiting && query_left == 0 && !serial_busy && !ser_valid) begin
      query_line    <= {"C ", hex4(writes), " ", hex4(reads), " ", hex4(pauses), " ", hex4(soeb_falls), " ",
                        hex4(glitches), " ", hex4(commands), " ", hex4(short_writes), " ", hex4(bounces), " ",
                        hex4(glitches_low), " ", hex4(glitches_after_d), " ", hex4(glitches_after_rs_rw), " ",
                        hex4(glitches_after_d7), " ", hex4(glitches_after_many), 8'h0D, 8'h0A};
      query_left    <= LINE;
      query_waiting <= 1'b0;
    end else if (query_push) begin
      query_line <= query_line << 8;
      query_left <= query_left - 1'b1;
    end
  end

  uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_tx (
    .clk(sysclk), .valid(!serial_empty), .data(tx_data), .ready(tx_ready), .tx(uart_rxd_out));
endmodule
