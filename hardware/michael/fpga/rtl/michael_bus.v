`timescale 1ns / 1ps
// The Michael FPGA bus's pins, as transfers (docs/michael-fpga-bus-plan.md, "The protocol").
//
// E's rising edge starts a transfer, chosen by RS and RW sampled with it. E is filtered: a level counts once
// it has held for E_FILTER samples (250 ns at 12 MHz), so glitches on the line can't make transfers; D, RS
// and RW are still taken at E's first high sample.
//   RW 0: a write. The byte on D is passed on with `wr`.
//   RW 1: a read. The byte is taken from `reply_byte` (RS 1) or `status_byte` (RS 0) as E rises, driven
//         onto D until E falls, and `rd_end` reports the end of the read.
//
// The data buffer (a 74LVC245, B side to Michael's port B, A side to the D pins) is turned around one step at
// a time, a clock apart, so that neither side ever has two drivers:
//   idle      buffer on, B to A (Michael to the FPGA); the FPGA doesn't drive D
//   read      buffer off; then A to B and the FPGA drives D; then the buffer on, while SOEB is high
//   E falls   buffer off; then B to A and the FPGA releases D; then the buffer on again
// While a read drives port B, SOEB low (the keyboard board driving port B) turns the buffer off at once:
// d_oeb is logic from the soeb pin, with no clock in the path (the SOEB interlock).
module michael_bus #(
  parameter E_FILTER = 3
) (
  input            clk,
  input      [7:0] d_in,        // the D pins
  output     [7:0] d_out,
  output reg       d_drive = 1'b0,
  input            e,
  input            rs,
  input            rw,
  input            soeb,
  output           d_oeb,       // the data buffer's /OE and DIR (1: A to B, the FPGA to Michael)
  output reg       d_dir = 1'b0,
  output reg       wr = 1'b0,   // one clock: a byte written
  output reg       wr_rs = 1'b0,
  output reg [7:0] wr_data = 8'h00,
  output reg       rd = 1'b0,   // one clock, as a read starts: the byte is taken this clock
  output reg       rd_end = 1'b0,  // one clock, as the read's E falls
  output reg       rd_rs = 1'b0,
  input      [7:0] reply_byte,
  input      [7:0] status_byte,
  output reg       paused = 1'b0,  // one clock: SOEB fell while a read was driving port B
  output reg       glitch = 1'b0   // one clock: E changed for less than E_FILTER samples (ignored)
);
  // Synchronised inputs: {d, e, rs, rw, soeb}
  reg [11:0] sync1 = 12'h001, sync2 = 12'h001;   // SOEB high: the keyboard board off
  always @(posedge clk) begin
    sync1 <= {d_in, e, rs, rw, soeb};
    sync2 <= sync1;
  end
  wire [7:0] d_s = sync2[11:4];
  wire e_s = sync2[3], rs_s = sync2[2], rw_s = sync2[1], soeb_s = sync2[0];
  reg  e_prev = 1'b0, soeb_prev = 1'b1;

  // E, filtered (e_f), with D, RS and RW as E first went high
  reg        e_f = 1'b0;
  reg  [$clog2(E_FILTER)-1:0] run = 0;   // samples in a row that differ from e_f
  reg  [7:0] d_at_e = 8'h00;
  reg        rs_at_e = 1'b0, rw_at_e = 1'b0;
  always @(posedge clk) begin
    glitch <= 1'b0;
    if (e_s != e_f) begin
      if (run == 0 && e_s) {d_at_e, rs_at_e, rw_at_e} <= {d_s, rs_s, rw_s};
      if (run == E_FILTER - 1) begin e_f <= e_s; run <= 0; end
      else run <= run + 1'b1;
    end else begin
      if (run != 0) glitch <= 1'b1;
      run <= 0;
    end
  end

  localparam IDLE = 3'd0, OFF_OUT = 3'd1, TURN_OUT = 3'd2, OUT = 3'd3, OFF_IN = 3'd4, TURN_IN = 3'd5;
  reg [2:0] state = IDLE;
  reg       oe_off = 1'b0;   // the buffer held off (between turnaround steps)
  reg [7:0] byte_out = 8'h00;

  assign d_out = byte_out;
  assign d_oeb = state == OUT ? !soeb : oe_off;

  always @(posedge clk) begin
    e_prev    <= e_f;
    soeb_prev <= soeb_s;
    wr        <= 1'b0;
    rd        <= 1'b0;
    rd_end    <= 1'b0;
    paused    <= 1'b0;
    case (state)
      IDLE:
        if (e_f && !e_prev) begin
          if (rw_at_e) begin
            rd       <= 1'b1;
            rd_rs    <= rs_at_e;
            byte_out <= rs_at_e ? reply_byte : status_byte;
            oe_off   <= 1'b1;
            state    <= OFF_OUT;
          end else begin
            wr      <= 1'b1;
            wr_rs   <= rs_at_e;
            wr_data <= d_at_e;
          end
        end
      OFF_OUT:  begin d_dir <= 1'b1; d_drive <= 1'b1; state <= TURN_OUT; end
      TURN_OUT: begin oe_off <= 1'b0; state <= OUT; end
      OUT: begin
        if (soeb_prev && !soeb_s) paused <= 1'b1;
        if (!e_f) begin
          oe_off <= 1'b1;
          rd_end <= 1'b1;
          state  <= OFF_IN;
        end
      end
      OFF_IN:  begin d_dir <= 1'b0; d_drive <= 1'b0; state <= TURN_IN; end
      TURN_IN: begin oe_off <= 1'b0; state <= IDLE; end
      default: state <= IDLE;
    endcase
  end
endmodule
