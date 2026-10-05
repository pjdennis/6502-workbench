`timescale 1ns / 1ps
// Drives text_grid.v from a file of operations (+ops=FILE: lines "op a b" in hex), as fast as it takes them,
// then writes what it holds (+out=FILE): every cell, the cursor, the region and the dirty cells. Run by
// test_text_grid.py, which compares them with text_screen.py.
module tb_text_grid;
  localparam ROWS = 20, COLS = 20;
  reg clk = 1'b0;
  always #41.667 clk = !clk;   // 12 MHz

  reg        push = 1'b0, rd = 1'b0;
  reg  [3:0] op = 0;
  reg  [7:0] a = 0, b = 0;
  reg  [4:0] rd_row = 0, rd_col = 0;
  wire       full, idle, text_mode, cursor_on, dirty;
  wire [4:0] cursor_row, cursor_col, dirty_row, dirty_col;
  wire [8:0] rd_cell;
  text_grid #(.ROWS(ROWS), .COLS(COLS), .QUEUE_DEPTH(16)) dut (
    .clk(clk), .push(push), .op(op), .a(a), .b(b), .full(full), .idle(idle), .text_mode(text_mode),
    .cursor_row(cursor_row), .cursor_col(cursor_col), .cursor_on(cursor_on), .top(), .bottom(), .offset(),
    .moving(), .hw_request(), .hw_up(), .hw_count(), .hw_ready(1'b1), .dirty(dirty),
    .dirty_row(dirty_row), .dirty_col(dirty_col), .take_dirty(1'b0), .rd(rd), .rd_row(rd_row),
    .rd_col(rd_col), .rd_cell(rd_cell));

  reg [8*256-1:0] ops_file, out_file;
  integer fin, fout, n, o, x, y, r, c;
  initial begin
    if (!$value$plusargs("ops=%s", ops_file) || !$value$plusargs("out=%s", out_file)) $fatal(1, "+ops and +out");
    fin = $fopen(ops_file, "r");
    @(posedge clk); #1;
    while ($fscanf(fin, "%h %h %h\n", o, x, y) == 3) begin
      while (full) begin @(posedge clk); #1; end
      op = o; a = x; b = y; push = 1'b1;
      @(posedge clk); #1 push = 1'b0;
    end
    $fclose(fin);
    while (!idle) begin @(posedge clk); #1; end
    fout = $fopen(out_file, "w");
    for (r = 0; r < ROWS; r = r + 1) begin
      for (c = 0; c < COLS; c = c + 1) begin
        rd_row = r; rd_col = c; rd = 1'b1;
        @(posedge clk); #1 rd = 1'b0;
        $fwrite(fout, "%03h ", rd_cell);
      end
      $fwrite(fout, "\n");
    end
    $fwrite(fout, "cursor %0d %0d %0d\nregion %0d %0d\nmode %0d\nmarks %b\n", cursor_row, cursor_col, cursor_on,
            dut.top, dut.bottom, text_mode, dut.marks);
    $fclose(fout);
    $finish;
  end
endmodule
