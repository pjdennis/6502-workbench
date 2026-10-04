`timescale 1ns / 1ps
`include "tb_util.vh"

// fifo.v: first word fall-through (dout is the oldest entry whenever empty is low), order kept across
// wrap-around, pushes when full and pops when empty ignored, and clear.
module tb_fifo;
  reg clk;
  `TB_CLOCK(clk, 41.667, 1_000_000)

  reg        clear = 1'b0, push = 1'b0, pop = 1'b0;
  reg  [7:0] din = 8'h00;
  wire [7:0] dout;
  wire       full, empty;
  wire [3:0] count;
  fifo #(.WIDTH(8), .DEPTH(8)) dut (.clk(clk), .clear(clear), .push(push), .din(din), .full(full), .pop(pop),
                                    .dout(dout), .empty(empty), .count(count));

  task step(input p, input [7:0] value, input q);
    begin push = p; din = value; pop = q; @(posedge clk); #1 push = 0; pop = 0; end
  endtask

  integer i;
  initial begin
    @(posedge clk); #1;
    `CHECK_EQ({empty, full, count}, {2'b10, 4'd0}, "empty at start")

    // A push shows at the head at once (after the clock), even into an empty queue
    step(1, 8'hA1, 0);
    `CHECK_EQ({empty, dout}, {1'b0, 8'hA1}, "first entry at the head")
    step(1, 8'hA2, 0);
    `CHECK_EQ(dout, 8'hA1, "still the first entry at the head")
    step(0, 0, 1);
    `CHECK_EQ({empty, dout, count}, {1'b0, 8'hA2, 4'd1}, "second entry after a pop")

    // Push and pop together with one entry: the new entry becomes the head
    step(1, 8'hA3, 1);
    `CHECK_EQ({empty, dout, count}, {1'b0, 8'hA3, 4'd1}, "push and pop together")
    step(0, 0, 1);
    `CHECK_EQ({empty, count}, {1'b1, 4'd0}, "empty again")
    step(0, 0, 1);
    `CHECK_EQ({empty, count}, {1'b1, 4'd0}, "a pop when empty is ignored")

    // Fill, overfill, then drain in order, twice so the pointers wrap
    repeat (2) begin
      for (i = 0; i < 9; i = i + 1) step(1, 8'h10 + i, 0);
      `CHECK_EQ({full, count}, {1'b1, 4'd8}, "full after 8 (the 9th ignored)")
      for (i = 0; i < 8; i = i + 1) begin
        `CHECK_EQ(dout, 8'h10 + i, "drained in order")
        step(0, 0, 1);
      end
      `CHECK_EQ(empty, 1'b1, "empty after draining")
    end

    // Clear empties it
    step(1, 8'h55, 0); step(1, 8'h66, 0);
    clear = 1; @(posedge clk); #1 clear = 0;
    `CHECK_EQ({empty, count}, {1'b1, 4'd0}, "empty after clear")
    step(1, 8'h77, 0);
    `CHECK_EQ(dout, 8'h77, "works after clear")
    `TB_PASS
  end
endmodule
