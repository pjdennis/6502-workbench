`timescale 1ns / 1ps
// A first-word-fall-through FIFO in block RAM: dout is the oldest entry whenever empty is low, and pop takes
// it. Pushes while full and pops while empty are ignored (callers that care watch full).
module fifo #(
  parameter WIDTH = 8,
  parameter DEPTH = 512   // a power of two
) (
  input                      clk,
  input                      clear,   // empties it
  input                      push,
  input      [WIDTH-1:0]     din,
  output                     full,
  input                      pop,
  output reg [WIDTH-1:0]     dout = 0,
  output                     empty,
  output reg [$clog2(DEPTH):0] count = 0
);
  localparam AW = $clog2(DEPTH);   // address width: the bits of a RAM index
  reg  [WIDTH-1:0] mem [0:DEPTH-1];
  reg  [AW-1:0]    wr = 0, rd = 0;
  assign full  = count == DEPTH;
  assign empty = count == 0;

  wire          do_push = push && !full;
  wire          do_pop  = pop && !empty;
  wire [AW-1:0] rd_next = rd + do_pop;

  always @(posedge clk)
    if (clear) begin
      wr <= 0; rd <= 0; count <= 0;
    end else begin
      if (do_push) begin
        mem[wr] <= din;
        wr <= wr + 1'b1;
      end
      rd    <= rd_next;
      count <= count + do_push - do_pop;
      // The head for next clock: the entry being written now if it lands there, else read from the RAM
      dout  <= do_push && wr == rd_next ? din : mem[rd_next];
    end
endmodule
