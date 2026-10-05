`timescale 1ns / 1ps
// Draws the text grid (text_grid.v) on the ILI9341, through display_spi.v's renderer input: each dirty cell
// as Michael's driver draws a character (gd_show_character in firmware/lib/graphics/graphics_display.inc),
// a window (CASET, PASET) and RAMWR, then its 12 columns of 16 pixels, white on black. Reverse video inverts
// a cell; the cursor inverts its bottom two rows, blinking every BLINK clocks (250 ms) and shown at once
// when it moves. A cell's bytes are a locked run, so nothing else reaches the display in the middle of one.
// On entering text mode it first sets the orientation Michael's driver uses (MADCTL: MY, MV, BGR).
//
// The display's hardware scroll follows the grid's scroll region and offset (text_grid.v's HW_SCROLL): the
// region is VSCRDEF's scroll area and VSCRSADD moves its picture, sent whenever they change, before any more
// cells are drawn. The display's frame memory lines run from the bottom row up (MADCTL's MY), so the rows
// below the region are the top fixed area, those above it the bottom one (hardware/michael/fpga/text/
// ili9341.py has the mapping, checked against the graphic driver's own scrolling). A cell is drawn in the
// memory row that the scroll shows where it belongs. The font is generated from firmware/lib/graphics/font_12x16.txt
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
  input      [4:0] top,            // the grid's scroll region, and how far its picture has scrolled
  input      [4:0] bottom,
  input      [4:0] offset,
  input            moving,         // the grid is moving cells: wait
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
  localparam [7:0] VSCRDEF = 8'h33;
  localparam PANEL_ROWS = 20;      // the display's 320 lines, in rows

  reg [15:0] font [0:2047];        // (code << 4) | column: the column's pixels, the top one in bit 0
  initial begin
`include "../build/font_12x16.vh"
  end

  localparam IDLE = 3'd0, SETUP = 3'd1, LOAD = 3'd2, HEAD = 3'd3, FONT = 3'd4, PIXELS = 3'd5, SCROLL = 3'd6;
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

  // The hardware scroll the display has (s_*), and whether the grid's differs
  reg  [4:0] s_top = 0, s_bottom = 0, s_offset = 0;
  reg        s_ok = 1'b0;
  wire scroll_due = text_mode && was_mode && (!s_ok || {top, bottom, offset} != {s_top, s_bottom, s_offset});

  wire cursor_shown = cursor_on && cursor_col < COLS;
  wire setup_due = text_mode && !was_mode;
  wire may_draw = state == IDLE && !setup_due && !scroll_due && text_mode && !moving;
  wire start_blink = may_draw && blink_due && cursor_shown;
  assign take_dirty = may_draw && !start_blink && dirty;
  assign rd = start_blink, rd_row = cursor_row, rd_col = cursor_col;
  assign idle = state == IDLE && !setup_due && !scroll_due && !(text_mode && (dirty || (blink_due && cursor_shown)));

  // The memory row where row r shows, through the hardware scroll. In the region, the scroll shows memory
  // row bottom - k, k being (offset + bottom - r) mod its height; elsewhere, row r. (Every function here takes
  // all it uses as arguments: simulation re-evaluates a function in a continuous assignment only when its
  // arguments change.)
  function [4:0] memory_row(input [4:0] r, input [4:0] t, input [4:0] b, input [4:0] o);
    reg [5:0] k;
    reg [4:0] height;
    begin
      height = b - t + 1'b1;
      k = o + (b - r);
      if (k >= height) k = k - height;
      memory_row = r < t || r > b ? r : b - k[4:0];
    end
  endfunction

  // The run's entries
  wire [4:0] p_row = memory_row(row, s_top, s_bottom, s_offset);
  wire [8:0] y0 = p_row * 16, y1 = y0 + 15;
  wire [8:0] x0 = col * 12, x1 = x0 + 11;
  // (Functions, not always @*, so that simulation has them from time 0)
  function [9:0] head_entry(input [3:0] n, input [8:0] y0, input [8:0] y1, input [8:0] x0, input [8:0] x1);
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
    setup_entry = n == 0 ? {COMMAND, MADCTL} : {DATA, MADCTL_TEXT};
  endfunction
  // VSCRDEF: the top fixed area (the rows below the region), the scroll area, the bottom fixed area (the rows
  // above it), in lines; then VSCRSADD: the scroll area's first line, offset rows into it
  wire [8:0] tfa = (PANEL_ROWS - 1 - s_bottom) * 16, vsa = (s_bottom - s_top + 1) * 16, bfa = s_top * 16,
             ssa = tfa + s_offset * 16;   // as latched for the run
  function [9:0] scroll_entry(input [3:0] n, input [8:0] tfa, input [8:0] vsa, input [8:0] bfa, input [8:0] ssa);
    case (n)
      4'd0: scroll_entry = {COMMAND, VSCRDEF};  4'd1: scroll_entry = {DATA, 7'd0, tfa[8]};
      4'd2: scroll_entry = {DATA, tfa[7:0]};    4'd3: scroll_entry = {DATA, 7'd0, vsa[8]};
      4'd4: scroll_entry = {DATA, vsa[7:0]};    4'd5: scroll_entry = {DATA, 7'd0, bfa[8]};
      4'd6: scroll_entry = {DATA, bfa[7:0]};    4'd7: scroll_entry = {COMMAND, VSCRSADD};
      4'd8: scroll_entry = {DATA, 7'd0, ssa[8]};  default: scroll_entry = {DATA, ssa[7:0]};
    endcase
  endfunction
  wire [9:0] head = head_entry(i, y0, y1, x0, x1), setup = setup_entry(i), scroll = scroll_entry(i, tfa, vsa, bfa, ssa);   // {kind, value}
  wire lit = column[y] ^ reverse ^ (cursor_here && y >= 16 - CURSOR_ROWS);
  wire [9:0] out = state == SETUP ? setup : state == SCROLL ? scroll : state == HEAD ? head : {DATA, {8{lit}}};
  assign r_valid = state == SETUP || state == SCROLL || state == HEAD || state == PIXELS;
  assign {r_kind, r_value} = out;
  wire last = state == SETUP ? i == 1 : state == SCROLL ? i == 9 : state == PIXELS && i == 11 && y == 15 && half;

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
        if (setup_due) begin was_mode <= 1'b1; s_ok <= 1'b0; i <= 0; state <= SETUP; end
        else if (scroll_due && !moving) begin
          {s_top, s_bottom, s_offset} <= {top, bottom, offset}; i <= 0; state <= SCROLL;
        end else begin
          if (!text_mode) was_mode <= 1'b0;
          if (start_blink || take_dirty) begin
            row <= start_blink ? cursor_row : dirty_row; col <= start_blink ? cursor_col : dirty_col;
            state <= LOAD;
          end
        end
      SETUP: if (r_take) begin i <= i + 1'b1; if (last) state <= IDLE; end
      SCROLL: if (r_take) begin
        i <= i + 1'b1;
        if (last) begin s_ok <= 1'b1; state <= IDLE; end
      end
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
