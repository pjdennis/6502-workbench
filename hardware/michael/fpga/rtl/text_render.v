`timescale 1ns / 1ps
// Draws the text grid (text_grid.v) on the ILI9341, through display_spi.v's renderer input: each dirty cell
// as Michael's driver draws a character (gd_show_character in firmware/lib/graphics/graphics_display.inc),
// a window (CASET, PASET) and RAMWR, then its 12 columns of 16 pixels, white on black. Reverse video inverts
// a cell; the cursor inverts its bottom two rows, blinking every BLINK clocks (250 ms) and shown at once
// when it moves. A cell's bytes are a locked run, so nothing else reaches the display in the middle of one.
// On entering text mode it first sets the orientation Michael's driver uses (MADCTL: MY, MV, BGR) and the
// hardware scroll to 0. The font is generated from firmware/lib/graphics/font_12x16.txt
// (tools/font_12x16.py vh hardware/michael/fpga/build/font_12x16.vh).
module text_render #(
  parameter ROWS  = 20,
  parameter COLS  = 20,
  parameter BLINK = 3_000_000
) (
  input            clk,
  input            text_mode,
  input      [4:0] cursor_row,
  input      [4:0] cursor_col,
  input            cursor_on,
  input            dirty,          // the grid's lowest dirty cell
  input      [4:0] dirty_row,
  input      [4:0] dirty_col,
  output           take_dirty,
  output           rd,             // or a cell to read (the cursor's, to blink it)
  output     [4:0] rd_row,
  output     [4:0] rd_col,
  input      [8:0] rd_cell,        // the next clock
  output           r_valid,        // display_spi.v's renderer input
  output     [1:0] r_kind,
  output     [7:0] r_value,
  output reg       r_lock = 1'b0,
  input            r_take,
  output           idle
);
  localparam [1:0] DATA = 2'd0, COMMAND = 2'd1;
  localparam [7:0] CASET = 8'h2A, PASET = 8'h2B, RAMWR = 8'h2C, MADCTL = 8'h36, VSCRSADD = 8'h37,
                   MADCTL_TEXT = 8'hA8;   // MY | MV | BGR, as gd_prepare_vertical
  localparam CURSOR_ROWS = 2;

  reg [15:0] font [0:2047];        // (code << 4) | column: the column's pixels, the top one in bit 0
  initial begin
`include "../build/font_12x16.vh"
  end

  localparam IDLE = 3'd0, SETUP = 3'd1, LOAD = 3'd2, HEAD = 3'd3, FONT = 3'd4, PIXELS = 3'd5;
  reg [2:0] state = IDLE;
  reg       was_mode = 1'b0, blink_on = 1'b1, blink_due = 1'b0;
  reg [$clog2(BLINK + 1)-1:0] blink_count = 0;
  reg [4:0] row = 0, col = 0, was_row = 0, was_col = 0;
  reg       was_on = 1'b0;
  reg [3:0] i = 0;                 // the run's entry (SETUP, HEAD), or the glyph's column (FONT, PIXELS)
  reg [3:0] y = 0;
  reg       half = 1'b0;
  reg [7:0] code = 8'h20;
  reg       reverse = 1'b0, cursor_here = 1'b0;
  reg [15:0] column = 0;

  wire cursor_shown = cursor_on && cursor_col < COLS;
  wire setup_due = text_mode && !was_mode;
  wire start_blink = state == IDLE && !setup_due && text_mode && blink_due && cursor_shown;
  assign take_dirty = state == IDLE && !setup_due && text_mode && !start_blink && dirty;
  assign rd = start_blink, rd_row = cursor_row, rd_col = cursor_col;
  assign idle = state == IDLE && !setup_due && !(text_mode && (dirty || (blink_due && cursor_shown)));

  // The run's entries
  wire [8:0] y0 = row * 16, y1 = y0 + 15;
  wire [8:0] x0 = col * 12, x1 = x0 + 11;
  // (Functions, not always @*, so that simulation has them from time 0)
  function [9:0] head_entry(input [3:0] n);   // {kind, value}
    case (n)
      4'd0: head_entry = {COMMAND, CASET};  4'd1: head_entry = {DATA, 7'd0, y0[8]};
      4'd2: head_entry = {DATA, y0[7:0]};   4'd3: head_entry = {DATA, 7'd0, y1[8]};
      4'd4: head_entry = {DATA, y1[7:0]};   4'd5: head_entry = {COMMAND, PASET};
      4'd6: head_entry = {DATA, 7'd0, x0[8]};  4'd7: head_entry = {DATA, x0[7:0]};
      4'd8: head_entry = {DATA, 7'd0, x1[8]};  4'd9: head_entry = {DATA, x1[7:0]};
      default: head_entry = {COMMAND, RAMWR};
    endcase
  endfunction
  function [9:0] setup_entry(input [3:0] n);
    case (n)
      4'd0: setup_entry = {COMMAND, MADCTL};    4'd1: setup_entry = {DATA, MADCTL_TEXT};
      4'd2: setup_entry = {COMMAND, VSCRSADD};  default: setup_entry = {DATA, 8'h00};
    endcase
  endfunction
  wire [9:0] head = head_entry(i), setup = setup_entry(i);
  wire lit = column[y] ^ reverse ^ (cursor_here && y >= 16 - CURSOR_ROWS);
  wire [9:0] out = state == SETUP ? setup : state == HEAD ? head : {DATA, {8{lit}}};
  assign r_valid = state == SETUP || state == HEAD || state == PIXELS;
  assign {r_kind, r_value} = out;
  wire last = state == SETUP ? i == 4 : state == PIXELS && i == 11 && y == 15 && half;

  always @(posedge clk) begin
    // The cursor blinks, and shows at once when it moves
    if ({cursor_row, cursor_col, cursor_on} != {was_row, was_col, was_on}) begin
      {was_row, was_col, was_on} <= {cursor_row, cursor_col, cursor_on};
      blink_on <= 1'b1; blink_count <= 0;
    end else if (blink_count == BLINK - 1) begin
      blink_count <= 0; blink_on <= !blink_on; blink_due <= 1'b1;
    end else blink_count <= blink_count + 1'b1;
    if (start_blink) blink_due <= 1'b0;

    if (r_take) r_lock <= !last;
    case (state)
      IDLE:
        if (setup_due) begin was_mode <= 1'b1; i <= 0; state <= SETUP; end
        else begin
          if (!text_mode) was_mode <= 1'b0;
          if (start_blink || take_dirty) begin
            row <= start_blink ? cursor_row : dirty_row; col <= start_blink ? cursor_col : dirty_col;
            state <= LOAD;
          end
        end
      SETUP: if (r_take) begin i <= i + 1'b1; if (last) state <= IDLE; end
      LOAD: begin
        code <= rd_cell[7:0]; reverse <= rd_cell[8];
        cursor_here <= cursor_shown && blink_on && cursor_row == row && cursor_col == col;
        i <= 0; state <= HEAD;
      end
      HEAD: if (r_take) begin
        if (i == 10) begin i <= 0; state <= FONT; end else i <= i + 1'b1;
      end
      FONT: begin                  // the column's pixels, read
        column <= font[{code[7] ? 7'd0 : code[6:0], i}];
        y <= 0; half <= 1'b0; state <= PIXELS;
      end
      PIXELS: if (r_take) begin
        half <= !half;
        if (half) begin
          if (y == 15) begin
            if (i == 11) state <= IDLE; else begin i <= i + 1'b1; state <= FONT; end
          end else y <= y + 1'b1;
        end
      end
      default: state <= IDLE;
    endcase
  end
endmodule
