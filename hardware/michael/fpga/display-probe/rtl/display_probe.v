`timescale 1ns / 1ps
// Display probe: a slow SPI master for the ILI9341, commanded from the PC over the Cmod's USB serial port
// (115200 8N1), to check the display and its wiring independently of Michael. Commands (bytes):
//   01 n b1..bn        write n bytes (MSB first) with the current CS and DC levels
//   02 n               read n bits (1-32) from SDO; replies "Rxxxxxxxx" (hex, last bit read in bit 0)
//   03 c               control lines: bit 0 CS, 1 DC, 2 RESET, 3 backlight, 4 swap the MOSI and SCK pins
//   04 h               SCK half period in 12 MHz clocks (1 = 6 MHz; default 6 = 1 MHz)
//   05 c2 c1 c0 b1 b0  write the byte pair b1 b0 c2c1c0 times (fills)
//   06                 replies "K00000000" once everything before it is done
// Replies are 11 characters including CR LF. Commands queue in a 64-byte buffer.
module display_probe #(
  parameter CLKS_PER_BIT = 104  // 115200 baud
) (
  input        sysclk,
  input  [7:0] d,          // Michael's inputs: unused here, present so the spi-display pins apply as they are
  input        e,
  input        csb,
  input        rstb,
  input        dc,
  input        bl,
  input        uart_txd_in,
  output       uart_rxd_out,
  output       lcd_cs,
  output       lcd_reset,
  output       lcd_dc,
  output       lcd_mosi,
  output       lcd_sck,
  output       lcd_led,
  input        lcd_miso,
  output       t_clk,
  output       t_cs,
  output       t_din,
  output [1:0] led,        // LD1: busy, LD2: display selected
  output       d_oeb,      // the data buffer: on, and Michael to the FPGA, as the interface has it
  output       d_dir
);
  localparam LEN = 11;
  assign {t_cs, t_clk, t_din} = 3'b100;
  assign {d_oeb, d_dir} = 2'b00;

  // Command bytes, queued
  wire       rx_valid;
  wire [7:0] rx_data;
  uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_rx (.clk(sysclk), .rx(uart_txd_in), .valid(rx_valid), .data(rx_data));
  reg  [7:0] queue [0:63];
  reg  [5:0] q_wr = 0, q_rd = 0;
  reg  [6:0] q_count = 0;
  wire       have = q_count != 0;
  wire [7:0] head = queue[q_rd];
  reg        take = 1'b0;
  always @(posedge sysclk) begin
    if (rx_valid && q_count != 64) begin
      queue[q_wr] <= rx_data;
      q_wr <= q_wr + 1'b1;
    end
    if (take) q_rd <= q_rd + 1'b1;
    q_count <= q_count + (rx_valid && q_count != 64) - take;
  end

  // Control lines and the SPI engine
  reg        cs = 1'b1, dc_level = 1'b1, reset_n = 1'b1, backlight = 1'b1, swap = 1'b0;
  reg  [7:0] half = 8'd6;
  reg        sck = 1'b0;
  reg  [7:0] shift = 0;
  reg  [5:0] bits_left = 0;
  reg        reading = 1'b0, high_phase = 1'b0;
  reg  [7:0] tick = 0;
  reg [31:0] received = 0;
  reg  [1:0] miso_sync = 2'b11;
  always @(posedge sysclk) miso_sync <= {miso_sync[0], lcd_miso};

  assign lcd_cs    = cs;
  assign lcd_dc    = dc_level;
  assign lcd_reset = reset_n;
  assign lcd_led   = backlight;
  wire   mosi      = reading ? 1'b0 : shift[7];
  assign lcd_mosi  = swap ? sck : mosi;
  assign lcd_sck   = swap ? mosi : sck;

  // Sequencer
  localparam S_IDLE = 0, S_ARG = 1, S_WRITE = 2, S_SHIFT = 3, S_REPLY = 4, S_FILL = 5;
  reg  [2:0] state = S_IDLE, after_shift = S_IDLE;
  reg  [7:0] cmd = 0, count = 0;
  reg  [2:0] args_left = 0;
  reg [39:0] args = 0;                       // fill: c2 c1 c0 b1 b0
  reg [23:0] fill_left = 0;
  reg        fill_second = 1'b0;
  reg        reply_k = 1'b0;

  wire line_busy;
  reg  line_start = 1'b0;
  reg  [8*LEN-1:0] line = 0;
  function [7:0] hex(input [3:0] n); hex = n < 10 ? "0" + n : "A" + n - 10; endfunction

  task begin_shift(input [7:0] value, input [5:0] n, input rd, input [2:0] next);
    begin
      shift <= value; bits_left <= n; reading <= rd; high_phase <= 1'b0; tick <= 0;
      sck <= 1'b0; after_shift <= next; state <= S_SHIFT;
    end
  endtask

  always @(posedge sysclk) begin
    take       <= 1'b0;
    line_start <= 1'b0;
    case (state)
      S_IDLE:
        if (have && !take) begin
          cmd  <= head;
          take <= 1'b1;
          case (head)
            8'h01, 8'h02, 8'h03, 8'h04: begin args_left <= 1; state <= S_ARG; end
            8'h05:                      begin args_left <= 5; state <= S_ARG; end
            8'h06:                      begin reply_k <= 1'b1; state <= S_REPLY; end
            default: ;                  // unknown: ignored
          endcase
        end
      S_ARG:
        if (have && !take) begin
          take <= 1'b1;
          args <= {args[31:0], head};
          args_left <= args_left - 1'b1;
          if (args_left == 1)
            case (cmd)
              8'h01: begin count <= head; state <= head == 0 ? S_IDLE : S_WRITE; end
              8'h02: begin received <= 0; begin_shift(8'h00, head[5:0], 1'b1, S_REPLY); reply_k <= 1'b0; end
              8'h03: begin {swap, backlight, reset_n, dc_level, cs} <= head[4:0]; state <= S_IDLE; end
              8'h04: begin half <= head == 0 ? 8'd1 : head; state <= S_IDLE; end
              8'h05: begin fill_left <= args[31:8]; fill_second <= 1'b0; state <= S_FILL; end  // c2 c1 c0: b0 is still arriving
              default: state <= S_IDLE;
            endcase
        end
      S_WRITE:
        if (count == 0) state <= S_IDLE;
        else if (have && !take) begin
          take  <= 1'b1;
          count <= count - 1'b1;
          begin_shift(head, 6'd8, 1'b0, S_WRITE);
        end
      S_FILL:  // args now hold c2 c1 c0 b1 b0 in bits 39..0
        if (fill_left == 0) state <= S_IDLE;
        else begin
          begin_shift(fill_second ? args[7:0] : args[15:8], 6'd8, 1'b0, S_FILL);
          if (fill_second) fill_left <= fill_left - 1'b1;
          fill_second <= !fill_second;
        end
      S_SHIFT:
        if (tick != half - 1) tick <= tick + 1'b1;
        else begin
          tick <= 0;
          if (!high_phase) begin
            sck <= 1'b1; high_phase <= 1'b1;
          end else begin                       // end of the high phase: sample, then fall
            if (reading) received <= {received[30:0], miso_sync[1]};
            sck <= 1'b0; high_phase <= 1'b0;
            shift <= {shift[6:0], 1'b0};
            bits_left <= bits_left - 1'b1;
            if (bits_left == 1) begin reading <= 1'b0; state <= after_shift; end
          end
        end
      S_REPLY:
        if (!line_busy && !line_start) begin
          line <= reply_k ? {"K00000000", 8'h0D, 8'h0A} :
                  {"R", hex(received[31:28]), hex(received[27:24]), hex(received[23:20]), hex(received[19:16]),
                   hex(received[15:12]), hex(received[11:8]), hex(received[7:4]), hex(received[3:0]), 8'h0D, 8'h0A};
          line_start <= 1'b1;
          state <= S_IDLE;
        end
      default: state <= S_IDLE;
    endcase
  end

  uart_line_tx #(.CLKS_PER_BIT(CLKS_PER_BIT), .LEN(LEN)) u_line (
    .clk(sysclk), .start(line_start), .line(line), .busy(line_busy), .tx(uart_rxd_out));

  assign led = {!cs, state != S_IDLE};
endmodule
