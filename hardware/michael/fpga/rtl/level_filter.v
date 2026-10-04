`timescale 1ns / 1ps
// Filters a synchronised input: a new level counts only once it has held for SAMPLES clocks in a row, so
// glitches (shorter changes) are ignored, and reported. For Michael's strobes, E: switching noise puts
// spikes of a few ns on it (hardware/michael/fpga/bus-check/README.md).
module level_filter #(
  parameter       SAMPLES = 3,
  parameter [0:0] INIT    = 1'b0
) (
  input      clk,
  input      in,                // already synchronised
  output reg level = INIT,      // the filtered level
  output reg glitch = 1'b0,     // one clock: a change that didn't last (ignored)
  output     starting           // this clock is the first sample of a change (which may yet not count)
);
  reg [$clog2(SAMPLES)-1:0] run = 0;   // samples in a row that differ from level
  assign starting = in != level && run == 0;
  always @(posedge clk) begin
    glitch <= 1'b0;
    if (in != level) begin
      if (run == SAMPLES - 1) begin level <= in; run <= 0; end
      else run <= run + 1'b1;
    end else begin
      if (run != 0) glitch <= 1'b1;
      run <= 0;
    end
  end
endmodule
