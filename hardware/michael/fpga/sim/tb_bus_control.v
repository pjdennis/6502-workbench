`timescale 1ns / 1ps
`include "tb_util.vh"

// bus_control.v with a display: the display commands ($1x) and their arguments turn into display queue
// entries; argument errors set ABANDONED and EXTRA; a full display queue sets OVERFLOW; ID reports the raw
// display and text mode. The text commands ($2x, GEOMETRY $30) turn into text grid operations, a command
// with its arguments each, PUT's data a character each; in text mode the raw display commands are refused
// (UNKNOWN), but for BACKLIGHT and DISP_RESET, which ends text mode. Transfers are driven directly, as michael_bus.v would make them.
module tb_bus_control;
  reg clk;
  `TB_CLOCK(clk, 41.667, 5_000_000)

  reg        wr = 0, wr_rs = 0, rd = 0, rd_end = 0, rd_rs = 0, disp_full = 0, text_full = 0;
  reg  [7:0] wr_data = 0;
  wire [7:0] reply_byte, status_byte, ser_data, disp_value, text_a, text_b;
  wire [1:0] disp_kind;
  wire [3:0] text_op;
  wire       ser_valid, disp_push, text_push;
  bus_control #(.DISPLAY(1), .TEXT(1), .TEXT_ROWS(20), .TEXT_COLS(20)) dut (
    .clk(clk), .wr(wr), .wr_rs(wr_rs), .wr_data(wr_data), .rd(rd), .rd_end(rd_end), .rd_rs(rd_rs),
    .reply_byte(reply_byte), .status_byte(status_byte), .busy(1'b0), .ser_valid(ser_valid), .ser_data(ser_data),
    .disp_push(disp_push), .disp_kind(disp_kind), .disp_value(disp_value), .disp_full(disp_full),
    .text_push(text_push), .text_op(text_op), .text_a(text_a), .text_b(text_b), .text_full(text_full));

  // What reaches the text grid
  reg [19:0] ops [0:63];
  integer    n_ops = 0, n_ops_checked = 0;
  always @(posedge clk) if (text_push) begin ops[n_ops] = {text_op, text_a, text_b}; n_ops = n_ops + 1; end
  task expect_op(input [3:0] o, input [7:0] a, input [7:0] b);
    begin
      `CHECK(n_ops_checked < n_ops, "text operation missing")
      `CHECK_EQ(ops[n_ops_checked], {o, a, b}, "text operation")
      n_ops_checked = n_ops_checked + 1;
    end
  endtask

  // What reaches the display queue
  localparam DATA = 2'd0, COMMAND = 2'd1, RESET = 2'd2, BACKLIGHT = 2'd3;
  reg [9:0] pushed [0:63];
  integer   n_pushed = 0, n_checked = 0;
  always @(posedge clk) if (disp_push) begin pushed[n_pushed] = {disp_kind, disp_value}; n_pushed = n_pushed + 1; end
  task expect_entry(input [1:0] k, input [7:0] v);
    begin
      `CHECK(n_checked < n_pushed, "display queue entry missing")
      `CHECK_EQ(pushed[n_checked], {k, v}, "display queue entry")
      n_checked = n_checked + 1;
    end
  endtask

  task write(input r, input [7:0] b);
    begin wr = 1; wr_rs = r; wr_data = b; @(posedge clk); #1 wr = 0; repeat (5) @(posedge clk); #1; end
  endtask
  task command(input [7:0] b); write(1'b0, b); endtask
  task data(input [7:0] b);    write(1'b1, b); endtask
  reg [7:0] got;
  task read(input r, output [7:0] b);
    begin
      rd = 1; rd_rs = r; b = r ? reply_byte : status_byte; @(posedge clk); #1 rd = 0;
      rd_end = 1; @(posedge clk); #1 rd_end = 0; repeat (3) @(posedge clk); #1;
    end
  endtask

  initial begin
    repeat (3) @(posedge clk); #1;

    // ID reports the raw display (capabilities bit 0)
    command(8'h01);
    read(1, got); read(1, got); read(1, got); read(1, got);
    `CHECK_EQ(got, 8'h03, "ID capabilities: raw display and text mode")

    // DISP_COMMAND: its argument is the command byte, then data bytes stream
    command(8'h11); data(8'h2A); data(8'h00); data(8'hEF);
    expect_entry(COMMAND, 8'h2A); expect_entry(DATA, 8'h00); expect_entry(DATA, 8'hEF);
    // DISP_DATA streams data bytes
    command(8'h12); data(8'h11); data(8'h22);
    expect_entry(DATA, 8'h11); expect_entry(DATA, 8'h22);
    // DISP_RESET and BACKLIGHT take their level as an argument
    command(8'h10); data(8'h00); command(8'h10); data(8'h01);
    expect_entry(RESET, 8'h00); expect_entry(RESET, 8'h01);
    command(8'h13); data(8'h80);
    expect_entry(BACKLIGHT, 8'h80);
    read(0, got);
    `CHECK_EQ(got, 8'h00, "clean status after the display commands")

    // Errors: a command before the previous one's argument (ABANDONED); data after a non-streaming
    // command's argument (EXTRA); a display entry with the queue full (OVERFLOW)
    command(8'h13); command(8'h00);
    read(0, got);
    `CHECK_EQ(got, 8'h01, "ABANDONED")
    command(8'h13); data(8'h40); data(8'h41);
    expect_entry(BACKLIGHT, 8'h40);
    read(0, got);
    `CHECK_EQ(got, 8'h04, "EXTRA")
    disp_full = 1; command(8'h12); data(8'h99); disp_full = 0;
    read(0, got);
    `CHECK_EQ(got, 8'h10, "OVERFLOW")
    expect_entry(DATA, 8'h99);   // offered to the queue, which dropped it

    // Text mode: each command an operation (op = code - $20), with its arguments
    command(8'h20);                               expect_op(4'h0, 8'h00, 8'h00);   // TEXT_ON
    command(8'h22); data(8'd3); data(8'd4);       expect_op(4'h2, 8'd3, 8'd4);     // GOTO row, column
    command(8'h23); data("H"); data("i");         expect_op(4'h3, "H", 8'h00); expect_op(4'h3, "i", 8'h00);
    command(8'h24);                               expect_op(4'h4, 8'h00, 8'h00);   // CLEAR
    command(8'h26); data(8'd2);                   expect_op(4'h6, 8'd2, 8'h00);    // INSERT count
    command(8'h28); data(8'd1); data(8'd9);       expect_op(4'h8, 8'd1, 8'd9);     // REGION top, bottom
    command(8'h2E); data(8'd1);                   expect_op(4'hE, 8'd1, 8'h00);    // CURSOR on
    command(8'h2F); data(8'd1);                   expect_op(4'hF, 8'd1, 8'h00);    // VIDEO reverse
    read(0, got);
    `CHECK_EQ(got, 8'h00, "clean status after the text commands")
    // GEOMETRY replies rows and columns, and isn't an operation
    command(8'h30);
    read(1, got);
    `CHECK_EQ(got, 8'd20, "GEOMETRY rows")
    read(1, got);
    `CHECK_EQ(got, 8'd20, "GEOMETRY columns")
    // In text mode the raw display commands are refused, but not BACKLIGHT
    command(8'h11); data(8'h2A); data(8'h00);
    read(0, got);
    `CHECK_EQ(got, 8'h02, "UNKNOWN: raw display command in text mode")
    command(8'h13); data(8'h40);
    expect_entry(BACKLIGHT, 8'h40);
    // A full text queue: OVERFLOW
    text_full = 1; command(8'h23); data("x"); text_full = 0;
    read(0, got);
    `CHECK_EQ(got, 8'h10, "OVERFLOW: text queue full")
    expect_op(4'h3, "x", 8'h00);
    // TEXT_OFF: raw display commands again
    command(8'h21);                               expect_op(4'h1, 8'h00, 8'h00);
    command(8'h12); data(8'h55);
    expect_entry(DATA, 8'h55);
    read(0, got);
    `CHECK_EQ(got, 8'h00, "raw display commands after TEXT_OFF")
    // DISP_RESET in text mode: the reset, and text mode ends (TEXT_OFF to the grid)
    command(8'h20);                               expect_op(4'h0, 8'h00, 8'h00);
    `CHECK_EQ(dut.text_mode, 1'b1, "text mode")
    command(8'h10);                               expect_op(4'h1, 8'h00, 8'h00);
    `CHECK_EQ(dut.text_mode, 1'b0, "text mode ended by DISP_RESET")
    data(8'h00);
    expect_entry(RESET, 8'h00);
    command(8'h11); data(8'h36);
    expect_entry(COMMAND, 8'h36);
    read(0, got);
    `CHECK_EQ(got, 8'h00, "raw display commands after DISP_RESET in text mode")
    `CHECK_EQ(n_checked, n_pushed, "no other display queue entries")
    `CHECK_EQ(n_ops_checked, n_ops, "no other text operations")
    `TB_PASS
  end
endmodule
