`timescale 1ns / 1ps
// The text grid, the renderer and the display queue, as the bus design has them: operations from a file
// (+ops=FILE: lines "op a b" in hex; op 10 waits until everything is idle) go in as fast as the grid takes
// them, and every byte the display receives is logged (+spi=FILE: lines "clock dc byte", the clock counted from
// the start), until everything is idle. Each wait ends with a line "wait clock".
// Run by test_text_render.py.
module tb_text_render;
  parameter ROWS = 20, COLS = 20;   // smaller in most tests, for speed
  parameter FRAME = 5000;           // the renderer's wait for the display's next frame: test_text_render.py's
                                    // frames are shorter
  reg clk = 1'b0;
  always #41.667 clk = !clk;   // 12 MHz

  reg        push = 1'b0;
  reg  [3:0] op = 0;
  reg  [7:0] a = 0, b = 0;
  wire       full, grid_idle, text_mode, cursor_on, dirty, take_dirty, rd, r_valid, r_lock, r_take, render_idle;
  wire       spi_busy, lcd_cs, lcd_reset, lcd_dc, lcd_mosi, lcd_sck, lcd_led;
  wire [4:0] cursor_row, cursor_col, dirty_row, dirty_col, rd_row, rd_col, top, bottom, offset;
  wire       moving, hw_request, hw_up, hw_ready;
  wire [4:0] hw_count;
  wire [8:0] rd_cell;
  wire [1:0] r_kind;
  wire [7:0] r_value;
  text_grid #(.ROWS(ROWS), .COLS(COLS), .QUEUE_DEPTH(64)) grid (
    .clk(clk), .push(push), .op(op), .a(a), .b(b), .full(full), .idle(grid_idle), .text_mode(text_mode),
    .cursor_row(cursor_row), .cursor_col(cursor_col), .cursor_on(cursor_on), .top(top), .bottom(bottom),
    .offset(offset), .moving(moving), .hw_request(hw_request), .hw_up(hw_up), .hw_count(hw_count),
    .hw_ready(hw_ready), .dirty(dirty), .dirty_row(dirty_row), .dirty_col(dirty_col),
    .take_dirty(take_dirty), .rd(rd), .rd_row(rd_row), .rd_col(rd_col), .rd_cell(rd_cell));
  text_render #(.ROWS(ROWS), .COLS(COLS), .BLINK(100_000_000), .FRAME(FRAME)) render (
    .clk(clk), .text_mode(text_mode), .cursor_row(cursor_row), .cursor_col(cursor_col), .cursor_on(cursor_on),
    .top(top), .bottom(bottom), .offset(offset), .moving(moving), .hw_request(hw_request), .hw_up(hw_up),
    .hw_count(hw_count), .hw_ready(hw_ready), .dirty(dirty), .dirty_row(dirty_row), .dirty_col(dirty_col), .take_dirty(take_dirty), .rd(rd),
    .rd_row(rd_row), .rd_col(rd_col), .rd_cell(rd_cell), .r_valid(r_valid), .r_kind(r_kind), .r_value(r_value),
    .r_lock(r_lock), .r_take(r_take), .idle(render_idle));
  display_spi #(.QUEUE_DEPTH(16)) display (
    .clk(clk), .push(1'b0), .kind(2'd0), .value(8'h00), .full(), .busy(spi_busy), .r_valid(r_valid),
    .r_kind(r_kind), .r_value(r_value), .r_lock(r_lock), .r_take(r_take), .lcd_cs(lcd_cs),
    .lcd_reset(lcd_reset), .lcd_dc(lcd_dc), .lcd_mosi(lcd_mosi), .lcd_sck(lcd_sck), .lcd_led(lcd_led));

  // Every entry the renderer hands over must be defined
  always @(posedge clk) if (r_take && $isunknown({r_kind, r_value})) $fatal(1, "renderer entry undefined at %t", $time);

  // The display's side: each byte, with its DC level
  integer fspi, bits = 0, clocks = 0;
  always @(posedge clk) clocks = clocks + 1;
  reg [7:0] sr = 0;
  always @(posedge lcd_sck) begin
    sr = {sr[6:0], lcd_mosi};
    bits = bits + 1;
    if (bits == 8) begin $fwrite(fspi, "%0d %0d %02h\n", clocks, lcd_dc, sr); bits = 0; end
  end

  integer quiet;
  task wait_quiet;
    begin
      quiet = 0;
      while (quiet < 100) begin
        @(posedge clk); #1;
        quiet = grid_idle && render_idle && !spi_busy && !r_valid ? quiet + 1 : 0;
      end
    end
  endtask

  reg [8*256-1:0] ops_file, spi_file;
  integer fin, o, x, y;
  initial begin
    if (!$value$plusargs("ops=%s", ops_file) || !$value$plusargs("spi=%s", spi_file)) $fatal(1, "+ops and +spi");
    fin = $fopen(ops_file, "r");
    fspi = $fopen(spi_file, "w");
    @(posedge clk); #1;
    while ($fscanf(fin, "%h %h %h\n", o, x, y) == 3) begin
      if (o == 'h10) begin wait_quiet; $fwrite(fspi, "wait %0d\n", clocks); end
      else begin
        while (full) begin @(posedge clk); #1; end
        op = o; a = x; b = y; push = 1'b1;
        @(posedge clk); #1 push = 1'b0;
      end
    end
    $fclose(fin);
    wait_quiet;
    $fclose(fspi);
    $finish;
  end
endmodule
