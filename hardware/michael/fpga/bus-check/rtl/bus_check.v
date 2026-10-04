`timescale 1ns / 1ps
// Bring-up check for the Michael FPGA bus's reads (stage 1 of docs/michael-fpga-bus-plan.md): the bus
// (michael_bus.v) with its control commands (bus_control.v): NOP, ID, RESET, ECHO, the status read, and
// SERIAL_SEND ($50, provisional), whose bytes go out of the Cmod's USB serial port (115200 8N1). Michael's
// test program reports its results that way.
//
// '?' from the PC adds a line of counts to the serial output, once it's idle:
//   "C wwww rrrr pppp ssss gggg cccc tttt"  in hex: transfers written, bytes read (replies and status), reads
//       paused by the SOEB interlock, SOEB's falls at any time (each keyboard byte Michael reads), glitches on E
//       (shorter than the bus's filter, so ignored), the writes that were commands, and writes whose E pulse
//       was shorter than SHORT_E (Michael's strobes last 3 us or more)
// The display is held idle. LD1 flashes on bus traffic; LD2 lights once a read has been paused.
module bus_check #(
  parameter CLKS_PER_BIT    = 104,      // 115200 baud
  parameter SERIAL_DEPTH    = 2048,
  parameter ACTIVITY_CYCLES = 600_000,  // 50 ms at 12 MHz
  parameter SHORT_E         = 18        // 1.5 us at 12 MHz
) (
  input        sysclk,
  inout  [7:0] d,
  input        e,
  input        rs,
  input        rw,
  input        soeb,
  input        csb,          // the spi-display interface's pins, unused here
  input        rstb,
  input        bl,
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
  localparam LINE = 38;

  assign {lcd_cs, lcd_reset, lcd_dc, lcd_mosi, lcd_sck, lcd_led} = 6'b110000;
  assign {t_cs, t_clk, t_din} = 3'b100;

  // The bus
  wire [7:0] d_out, wr_data, reply_byte, status_byte, ser_data;
  wire       d_drive, wr, wr_rs, rd, rd_end, rd_rs, paused, glitch, e_filtered, ser_valid;
  assign d = d_drive ? d_out : 8'bz;

  michael_bus bus (
    .clk(sysclk), .d_in(d), .d_out(d_out), .d_drive(d_drive), .e(e), .rs(rs), .rw(rw), .soeb(soeb),
    .d_oeb(d_oeb), .d_dir(d_dir), .wr(wr), .wr_rs(wr_rs), .wr_data(wr_data), .rd(rd), .rd_end(rd_end),
    .rd_rs(rd_rs), .reply_byte(reply_byte), .status_byte(status_byte), .paused(paused), .glitch(glitch),
    .e_filtered(e_filtered));

  wire serial_busy;
  bus_control control (
    .clk(sysclk), .wr(wr), .wr_rs(wr_rs), .wr_data(wr_data), .rd(rd), .rd_end(rd_end), .rd_rs(rd_rs),
    .reply_byte(reply_byte), .status_byte(status_byte), .busy(serial_busy),
    .ser_valid(ser_valid), .ser_data(ser_data));

  // Counts
  reg [15:0] writes = 0, reads = 0, pauses = 0, soeb_falls = 0, glitches = 0, commands = 0, short_writes = 0;
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
    if (glitch) glitches <= glitches + 1'b1;
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

  reg              query_waiting = 1'b0;
  reg [8*LINE-1:0] query_line = 0;
  reg [5:0]        query_left = 0;
  wire             query_push = query_left != 0 && !ser_valid;

  // Serial output queue (block RAM), drained into the UART
  localparam AW = $clog2(SERIAL_DEPTH);
  reg  [7:0]  fifo [0:SERIAL_DEPTH-1];
  reg  [7:0]  head = 8'h00, tx_data = 8'h00;
  reg  [AW-1:0] f_wr = 0, f_rd = 0;
  reg  [AW:0]   f_count = 0;
  reg         fetch = 1'b0, tx_valid = 1'b0;
  wire        tx_ready;
  wire        push = ser_valid || query_push;
  wire        stored = push && f_count != SERIAL_DEPTH;
  assign serial_busy = f_count != 0 || tx_valid || !tx_ready;

  always @(posedge sysclk) begin
    if (rx_valid && rx_data == "?") query_waiting <= 1'b1;
    if (query_waiting && query_left == 0 && !serial_busy && !ser_valid) begin
      query_line    <= {"C ", hex4(writes), " ", hex4(reads), " ", hex4(pauses), " ", hex4(soeb_falls), " ",
                        hex4(glitches), " ", hex4(commands), " ", hex4(short_writes), 8'h0D, 8'h0A};
      query_left    <= LINE;
      query_waiting <= 1'b0;
    end else if (query_push) begin
      query_line <= query_line << 8;
      query_left <= query_left - 1'b1;
    end

    if (stored) begin
      fifo[f_wr] <= ser_valid ? ser_data : query_line[8*LINE-1 -: 8];
      f_wr <= f_wr + 1'b1;
    end
    head    <= fifo[f_rd];
    f_count <= f_count + stored - fetch;
    if (fetch) f_rd <= f_rd + 1'b1;

    fetch <= 1'b0;
    if (tx_valid && tx_ready) tx_valid <= 1'b0;
    if (fetch) begin
      tx_valid <= 1'b1;
      tx_data  <= head;
    end else if (!tx_valid && tx_ready && f_count != 0)
      fetch <= 1'b1;   // head shows fifo[f_rd] next clock
  end

  uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_tx (
    .clk(sysclk), .valid(tx_valid), .data(tx_data), .ready(tx_ready), .tx(uart_rxd_out));
endmodule
