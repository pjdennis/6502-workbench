`timescale 1ns / 1ps
// Bring-up check for the spi-display interface's inputs. Reports over the Cmod's USB serial port (115200 8N1):
//   "S dd ecrdb"  the 13 inputs held steady for SETTLE_CYCLES (1 ms) and differ from the last state reported;
//                 also sent for '?'. dd = port B in hex, then E, CSB, RSTB, DC and backlight as 0/1.
//   "B dd ecrdb"  a byte the spi-display bridge latched, with the control levels at that moment.
//   "! OVERFLOW"  the event buffer filled and events were lost.
// Lines are 12 characters including CR LF. Events wait in a FIFO, so Michael's fastest loop (a byte every
// 4.5 us) is reported in full. The display outputs are held idle.
module input_check #(
  parameter SETTLE_CYCLES = 12_000,  // 1 ms at 12 MHz
  parameter CLKS_PER_BIT  = 104,     // 115200 baud
  parameter FIFO_DEPTH    = 2048
) (
  input        sysclk,
  input  [7:0] d,
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
  output       t_clk,
  output       t_cs,
  output       t_din,
  output [1:0] led,
  output       d_oeb,  // the data buffer: on, and Michael to the FPGA
  output       d_dir
);
  localparam LEN = 12;
  localparam [1:0] KIND_STATE = 0, KIND_BYTE = 1;

  assign {lcd_cs, lcd_reset, lcd_dc, lcd_mosi, lcd_sck, lcd_led} = 6'b110000;
  assign {t_cs, t_clk, t_din} = 3'b100;
  assign led = 2'b00;
  assign {d_oeb, d_dir} = 2'b00;

  // Inputs, synchronised: {d[7:0], e, csb, rstb, dc, bl}
  reg [12:0] sync1 = 0, inputs = 0;
  always @(posedge sysclk) begin
    sync1  <= {d, e, csb, rstb, dc, bl};
    inputs <= sync1;
  end

  // Settled states
  reg [12:0] prev = 0, reported = 0;
  reg        reported_any = 1'b0;
  reg [$clog2(SETTLE_CYCLES + 1)-1:0] stable = 0;
  wire settles_now = inputs == prev && stable == SETTLE_CYCLES - 1;
  wire state_event = settles_now && (!reported_any || inputs != reported);
  always @(posedge sysclk) begin
    prev <= inputs;
    if (inputs != prev)             stable <= 0;
    else if (stable != SETTLE_CYCLES) stable <= stable + 1'b1;
    if (state_event) begin
      reported     <= inputs;
      reported_any <= 1'b1;
    end
  end

  // Bytes, as the spi-display bridge latches them
  wire accepted;
  spi_bridge bridge (
    .clk(sysclk), .d(d), .e(e), .csb(csb), .rstb(rstb), .dc(dc), .selected(), .accepted(accepted),
    .lcd_cs(), .lcd_reset(), .lcd_dc(), .lcd_mosi(), .lcd_sck());

  // '?' from the host
  wire       rx_valid;
  wire [7:0] rx_data;
  uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_rx (.clk(sysclk), .rx(uart_txd_in), .valid(rx_valid), .data(rx_data));
  wire query_event = rx_valid && rx_data == "?";

  // One event enters the FIFO per clock: a byte first; a state or query waits a clock if they coincide
  reg        state_pending = 1'b0, query_pending = 1'b0;
  reg [12:0] state_value = 0, query_value = 0;
  wire        push = accepted || state_pending || query_pending;
  wire [14:0] push_entry = accepted      ? {KIND_BYTE, d, inputs[4:2], dc, inputs[0]} :
                           state_pending ? {KIND_STATE, state_value} : {KIND_STATE, query_value};
  always @(posedge sysclk) begin
    if (state_event)                          {state_pending, state_value} <= {1'b1, inputs};
    else if (!accepted && state_pending)      state_pending <= 1'b0;
    if (query_event)                          {query_pending, query_value} <= {1'b1, inputs};
    else if (!accepted && !state_pending && query_pending) query_pending <= 1'b0;
  end

  // Event FIFO (block RAM)
  localparam AW = $clog2(FIFO_DEPTH);
  reg [14:0] fifo [0:FIFO_DEPTH-1];
  reg [14:0] head = 0;
  reg [AW-1:0] wr = 0, rd = 0;
  reg [AW:0]   count = 0;
  reg          overflow = 1'b0, fetch = 1'b0, line_start = 1'b0;
  wire         line_busy;
  wire         full = count == FIFO_DEPTH;
  wire         pop = fetch;
  wire         stored = push && !full;

  always @(posedge sysclk) begin
    if (stored) begin
      fifo[wr] <= push_entry;
      wr <= wr + 1'b1;
    end
    head  <= fifo[rd];
    count <= count + stored - pop;
    if (pop) rd <= rd + 1'b1;
  end

  // Report lines
  function [7:0] hex(input [3:0] n); hex = n < 10 ? "0" + n : "A" + n - 10; endfunction
  function [8*LEN-1:0] format(input [14:0] ev);
    format = {ev[14:13] == KIND_BYTE ? "B" : "S", " ", hex(ev[12:9]), hex(ev[8:5]), " ",
              "0" + ev[4], "0" + ev[3], "0" + ev[2], "0" + ev[1], "0" + ev[0], 8'h0D, 8'h0A};
  endfunction

  reg [8*LEN-1:0] line = 0;
  always @(posedge sysclk) begin
    line_start <= 1'b0;
    fetch      <= 1'b0;
    if (push && full) overflow <= 1'b1;
    if (fetch) begin
      line       <= format(head);
      line_start <= 1'b1;
    end else if (!line_busy && !line_start) begin
      if (overflow) begin
        line       <= {"! OVERFLOW", 8'h0D, 8'h0A};
        line_start <= 1'b1;
        overflow   <= 1'b0;
      end else if (count != 0)
        fetch <= 1'b1;  // head shows fifo[rd] next clock
    end
  end

  uart_line_tx #(.CLKS_PER_BIT(CLKS_PER_BIT), .LEN(LEN)) u_line (
    .clk(sysclk), .start(line_start), .line(line), .busy(line_busy), .tx(uart_rxd_out));
endmodule
