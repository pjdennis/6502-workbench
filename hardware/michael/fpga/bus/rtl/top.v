`timescale 1ns / 1ps
// The Michael FPGA bus with the display (stage 2 of docs/michael-fpga-bus-plan.md), replacing spi-display:
// michael_bus.v (the pins as transfers), bus_control.v (the commands, the reply queue and the status, with the
// raw display commands) and display_spi.v (the ILI9341, fed from a queue). The Cmod's USB serial port (115200
// 8N1) carries SERIAL_SEND's bytes to the PC and the debug port (debug_port.v), through which the PC makes
// the same transactions as Michael. BUSY is set while the display queue or the serial output has work.
//
// The inputs that were the spi-display interface's CSB, RSTB and backlight (now PA1, PA2 and the backlight
// tie) are unused: the display's chip select, reset and backlight are commands now. LD1 flashes on bus
// traffic, LD2 while the display is busy.
module top #(
  parameter CLKS_PER_BIT    = 104,      // 115200 baud
  parameter SERIAL_DEPTH    = 2048,
  parameter DISPLAY_DEPTH   = 512,
  parameter ACTIVITY_CYCLES = 600_000   // 50 ms at 12 MHz
) (
  input        sysclk,       // 12 MHz
  inout  [7:0] d,
  input        e,
  input        rs,
  input        rw,
  input        soeb,
  input        pa1,          // unused
  input        pa2,          // unused (Michael's LED)
  input        backlight_tie,// unused
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
  output       t_clk,        // touch controller, held idle
  output       t_cs,
  output       t_din,
  output [1:0] led
);
  assign {t_cs, t_clk, t_din} = 3'b100;

  // The bus
  wire [7:0] d_out, m_wr_data, reply_byte, status_byte, ser_data, disp_value;
  wire [1:0] disp_kind;
  wire       d_drive, m_wr, m_wr_rs, m_rd, m_rd_end, m_rd_rs, ser_valid, disp_push, disp_full, disp_busy, serial_busy;
  assign d = d_drive ? d_out : 8'bz;

  michael_bus bus (
    .clk(sysclk), .d_in(d), .d_out(d_out), .d_drive(d_drive), .e(e), .rs(rs), .rw(rw), .soeb(soeb),
    .hold_off(1'b0), .d_oeb(d_oeb), .d_dir(d_dir), .wr(m_wr), .wr_rs(m_wr_rs), .wr_data(m_wr_data), .rd(m_rd),
    .rd_end(m_rd_end), .rd_rs(m_rd_rs), .reply_byte(reply_byte), .status_byte(status_byte), .paused(),
    .glitch(), .e_filtered());

  // The debug port's transactions, in clocks without one of Michael's
  wire [7:0] rx_data, p_wr_data, p_out_data;
  wire       rx_valid, p_wr, p_wr_rs, p_rd, p_rd_end, p_rd_rs, p_out_valid, serial_full;
  wire       michael = m_wr || m_rd || m_rd_end;
  uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_rx (.clk(sysclk), .rx(uart_txd_in), .valid(rx_valid), .data(rx_data));
  debug_port debug (
    .clk(sysclk), .rx_valid(rx_valid), .rx_data(rx_data), .bus_busy(michael), .wr(p_wr), .wr_rs(p_wr_rs),
    .wr_data(p_wr_data), .rd(p_rd), .rd_end(p_rd_end), .rd_rs(p_rd_rs), .reply_byte(reply_byte),
    .status_byte(status_byte), .out_valid(p_out_valid), .out_data(p_out_data),
    .out_ready(!ser_valid && !serial_full));
  wire       wr      = m_wr || p_wr;
  wire       wr_rs   = m_wr ? m_wr_rs : p_wr_rs;
  wire [7:0] wr_data = m_wr ? m_wr_data : p_wr_data;
  wire       rd      = m_rd || p_rd;
  wire       rd_end  = m_rd_end || p_rd_end;
  wire       rd_rs   = m_rd || m_rd_end ? m_rd_rs : p_rd_rs;

  bus_control #(.DISPLAY(1)) control (
    .clk(sysclk), .wr(wr), .wr_rs(wr_rs), .wr_data(wr_data), .rd(rd), .rd_end(rd_end), .rd_rs(rd_rs),
    .reply_byte(reply_byte), .status_byte(status_byte), .busy(disp_busy || serial_busy),
    .ser_valid(ser_valid), .ser_data(ser_data), .disp_push(disp_push), .disp_kind(disp_kind),
    .disp_value(disp_value), .disp_full(disp_full));

  // The display
  display_spi #(.QUEUE_DEPTH(DISPLAY_DEPTH)) display (
    .clk(sysclk), .push(disp_push), .kind(disp_kind), .value(disp_value), .full(disp_full), .busy(disp_busy),
    .lcd_cs(lcd_cs), .lcd_reset(lcd_reset), .lcd_dc(lcd_dc), .lcd_mosi(lcd_mosi), .lcd_sck(lcd_sck),
    .lcd_led(lcd_led));

  // SERIAL_SEND's bytes and the debug port's answers, queued for the UART
  wire [7:0] tx_data;
  wire       tx_ready, serial_empty;
  fifo #(.WIDTH(8), .DEPTH(SERIAL_DEPTH)) serial_out (
    .clk(sysclk), .clear(1'b0), .push(ser_valid || p_out_valid), .din(ser_valid ? ser_data : p_out_data),
    .full(serial_full), .pop(!serial_empty && tx_ready),
    .dout(tx_data), .empty(serial_empty), .count());
  assign serial_busy = !serial_empty || !tx_ready;
  uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_tx (
    .clk(sysclk), .valid(!serial_empty), .data(tx_data), .ready(tx_ready), .tx(uart_rxd_out));

  // LEDs: bus traffic, and the display working through its queue, stretched so they can be seen
  reg [$clog2(ACTIVITY_CYCLES)-1:0] bus_seen = 0, display_seen = 0;
  always @(posedge sysclk) begin
    if (wr || rd)            bus_seen <= ACTIVITY_CYCLES - 1;
    else if (bus_seen != 0)  bus_seen <= bus_seen - 1'b1;
    if (disp_busy)               display_seen <= ACTIVITY_CYCLES - 1;
    else if (display_seen != 0)  display_seen <= display_seen - 1'b1;
  end
  assign led = {display_seen != 0, bus_seen != 0};
endmodule
