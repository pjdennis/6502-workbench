`timescale 1ns / 1ps
// The FPGA bus's text mode: the character grid that the text commands ($2x in docs/michael-fpga-bus-plan.md)
// change, as hardware/michael/fpga/text/text_screen.py models it (the ROM's LCD screen's rules, with reverse
// video, 0-based). Operations queue, so Michael never waits; each runs in turn, the shifting ones a cell
// per clock or two.
//
// The renderer reads the grid through its own port, and finds what to draw through the dirty bits: a cell
// is marked when what's written changes it (a cell written with what it holds keeps its mark, set or not, so
// rewriting the same text or moving blanks onto blanks draws nothing), and so are the cells a shown cursor
// leaves and reaches (or shows or hides on). TEXT_ON marks every cell.
// take_dirty clears the lowest dirty cell's bit and reads it; a cell marked in the same clock stays marked.
//
// With HW_SCROLL, scrolling the whole region (SCROLL_UP and SCROLL_DOWN, and INSERT_LINES and DELETE_LINES
// from its top row) moves the cells with their marks, marks only the rows that come in blank, and changes
// offset instead: the renderer has the display's hardware scroll move the region's picture by as many rows.
// The cursor's cell, and the cell its picture moved to, are marked. Changing the region while offset isn't
// 0 sets it back to 0 and marks every cell. The renderer takes no cells while the grid is moving cells.
module text_grid #(
  parameter ROWS        = 20,
  parameter COLS        = 20,
  parameter QUEUE_DEPTH = 512,
  parameter HW_SCROLL   = 1
) (
  input            clk,
  input            push,           // an operation: op = the command's code - $20, with its arguments
  input      [3:0] op,
  input      [7:0] a,
  input      [7:0] b,
  output           full,
  output           idle,           // nothing queued or under way
  output reg       text_mode = 1'b0,
  output reg [4:0] cursor_row = 5'd0,
  output reg [4:0] cursor_col = 5'd0,   // COLS: past the end of the row
  output reg       cursor_on = 1'b0,
  output reg [4:0] top = 5'd0,     // the scroll region
  output reg [4:0] bottom = ROWS - 1,
  output reg [4:0] offset = 5'd0,  // rows the region's picture has scrolled (HW_SCROLL)
  output           moving,         // cells are moving: the renderer waits
  output           dirty,          // a cell to draw: dirty_row, dirty_col
  output     [4:0] dirty_row,
  output     [4:0] dirty_col,
  input            take_dirty,     // clears its bit, and reads it: rd_cell the next clock
  input            rd,             // or reads rd_row, rd_col (for tests)
  input      [4:0] rd_row,
  input      [4:0] rd_col,
  output reg [8:0] rd_cell = 9'h020     // {reverse, character}
);
  localparam [3:0] TEXT_ON = 4'h0, TEXT_OFF = 4'h1, GOTO = 4'h2, PUT = 4'h3, CLEAR = 4'h4, CLEAR_EOL = 4'h5,
                   INSERT = 4'h6, DELETE = 4'h7, REGION = 4'h8, REGION_RESET = 4'h9, SCROLL_UP = 4'hA,
                   SCROLL_DOWN = 4'hB, INSERT_LINES = 4'hC, DELETE_LINES = 4'hD, CURSOR = 4'hE, VIDEO = 4'hF;
  localparam [8:0] BLANK = 9'h020;
  localparam [7:0] BS = 8'h08, LF = 8'h0A, CR = 8'h0D;
  localparam LAST_ROW = ROWS - 1, LAST_COL = COLS - 1;

  // The queue of operations
  wire [19:0] entry;
  wire        empty;
  reg         pop = 1'b0;
  fifo #(.WIDTH(20), .DEPTH(QUEUE_DEPTH)) queue (
    .clk(clk), .clear(1'b0), .push(push), .din({op, a, b}), .full(full), .pop(pop), .dout(entry),
    .empty(empty), .count());
  wire [3:0] e_op = entry[19:16];
  wire [7:0] e_a = entry[15:8], e_b = entry[7:0];

  // The grid: {row, col} -> {reverse, character}. A write (we) reads the cell first, and lands the next clock
  // (wb), marked by what it held
  reg  [8:0] cells [0:1023];       // undefined until TEXT_ON clears it
  reg        we = 1'b0, wb = 1'b0;
  reg  [4:0] w_row = 0, w_col = 0, wb_row = 0, wb_col = 0;
  reg  [8:0] w_cell = BLANK, r_cell = BLANK, wb_cell = BLANK, wb_old = BLANK;
  wire [9:0] src;                  // the shifting engine's source cell, read for the next clock
  always @(posedge clk) begin
    wb <= we;
    if (we) begin {wb_row, wb_col, wb_cell} <= {w_row, w_col, w_cell}; wb_old <= cells[{w_row, w_col}]; end
    if (wb) cells[{wb_row, wb_col}] <= wb_cell;
    r_cell <= cells[src];
  end
  wire [4:0] p_row = take_dirty ? dirty_row : rd_row, p_col = take_dirty ? dirty_col : rd_col;
  always @(posedge clk) if (take_dirty || rd) rd_cell <= cells[{p_row, p_col}];

  // State
  reg       reverse = 1'b0;

  // The shifting engine: the block of cells rows r0-r1, columns c0-c1 moves by n rows (vertical) or columns,
  // towards its start (forward: each cell takes the one n after it) or its end; blanks fill in
  localparam IDLE = 2'd0, MOVE = 2'd1, MOVE_WRITE = 2'd2;
  reg [1:0] state = IDLE;
  reg       vertical = 1'b0, forward = 1'b0;
  reg [4:0] r0 = 0, r1 = 0, c0 = 0, c1 = 0, row = 0, col = 0;
  reg [7:0] n = 0;
  // The source is n cells away, and in the block if the block has that many beyond the cell
  wire [4:0] beyond = vertical ? (forward ? r1 - row : row - r0) : (forward ? c1 - col : col - c0);
  wire       src_ok = n <= beyond;
  wire [4:0] step_n = n[4:0];      // within the block when src_ok
  wire [4:0] src_row = !vertical ? row : forward ? row + step_n : row - step_n;
  wire [4:0] src_col = vertical ? col : forward ? col + step_n : col - step_n;
  assign src = {src_row, src_col};
  wire       last = forward ? row == r1 && col == c1 : row == r0 && col == c0;
  assign idle = state == IDLE && empty && !pop && !we && !wb;
  assign moving = state != IDLE;

  reg       carry = 1'b0, scrolled = 1'b0, mark_all = 1'b0;
  reg [4:0] next_offset = 5'd0;

  task start(input v, input f, input [4:0] top_row, input [4:0] bottom_row, input [4:0] first_col,
             input [4:0] last_col, input [7:0] count);
    begin
      vertical <= v; forward <= f; r0 <= top_row; r1 <= bottom_row; c0 <= first_col; c1 <= last_col;
      n <= count; row <= f ? top_row : bottom_row; col <= f ? first_col : last_col;
      carry <= 1'b0;
      if (count != 0) state <= MOVE;
    end
  endtask

  // A scroll of the region's rows from_row down (up: the content moves up), by the hardware scroll when the
  // whole region moves by fewer rows than it has
  wire [4:0] height = bottom - top + 1'b1;
  task scroll(input up, input [4:0] from_row, input [7:0] count);
    begin
      start(1'b1, up, from_row, bottom, 0, LAST_COL, count);
      if (HW_SCROLL && from_row == top && count != 0 && count < height) begin
        carry <= 1'b1;
        next_offset <= up ? (offset >= count ? offset - count[4:0] : offset + height - count[4:0])
                          : (offset + count[4:0] >= height ? offset + count[4:0] - height : offset + count[4:0]);
      end
    end
  endtask

  // A new region: with the picture scrolled, back to no scroll, and every cell redrawn
  task set_region(input [4:0] new_top, input [4:0] new_bottom);
    begin
      top <= new_top; bottom <= new_bottom; cursor_row <= 0; cursor_col <= 0;
      if ({new_top, new_bottom} != {top, bottom} && offset != 0) begin offset <= 0; mark_all <= 1'b1; end
    end
  endtask

  // The end of a move
  task finish;
    begin
      state <= IDLE;
      if (carry) begin offset <= next_offset; carry <= 1'b0; scrolled <= 1'b1; end
    end
  endtask

  // Marking: cells written, and the cursor's old and new cells when it changes. Bit row * COLS + col
  reg [ROWS*COLS-1:0] marks = 0;
  reg  [4:0] was_row = 0, was_col = 0;
  reg        was_on = 1'b0;
  wire       cursor_moved = {cursor_row, cursor_col, cursor_on} != {was_row, was_col, was_on};
  reg        w_carry = 1'b0, wb_carry = 1'b0;   // the written cell's mark is w_mark (carried with the cell),
  reg        w_mark = 1'b1, wb_mark = 1'b1;     // not set by a change
  // After a hardware scroll, where the cursor's picture went: n rows up or down, if still in the block
  wire [5:0] moved_row = forward ? {1'b0, cursor_row} - n[4:0] : {1'b0, cursor_row} + n[4:0];
  wire       cursor_in_block = cursor_col < COLS && cursor_row >= r0 && cursor_row <= r1;
  wire       moved_in_block = forward ? cursor_row >= r0 + n[4:0] : moved_row <= r1;

  // The lowest dirty cell (functions, not always @*, so that simulation has it from time 0)
  function [4:0] first_row(input [ROWS*COLS-1:0] m);
    integer r;
    begin
      first_row = 0;
      for (r = LAST_ROW; r >= 0; r = r - 1) if (m[r*COLS +: COLS] != 0) first_row = r;
    end
  endfunction
  function [4:0] first_col(input [COLS-1:0] m);
    integer c;
    begin
      first_col = 0;
      for (c = LAST_COL; c >= 0; c = c - 1) if (m[c]) first_col = c;
    end
  endfunction
  assign dirty = marks != 0, dirty_row = first_row(marks), dirty_col = first_col(marks[dirty_row*COLS +: COLS]);

  always @(posedge clk) begin
    if (take_dirty) marks[dirty_row*COLS + dirty_col] <= 1'b0;
    if (we) {wb_carry, wb_mark} <= {w_carry, w_mark};
    if (wb) marks[wb_row*COLS + wb_col] <= wb_carry ? wb_mark : marks[wb_row*COLS + wb_col] || wb_cell != wb_old;
    if (scrolled && cursor_in_block) begin
      marks[cursor_row*COLS + cursor_col] <= 1'b1;
      if (moved_in_block) marks[moved_row[4:0]*COLS + cursor_col] <= 1'b1;
    end
    if (cursor_moved) begin
      if (was_on && was_col < COLS) marks[was_row*COLS + was_col] <= 1'b1;
      if (cursor_on && cursor_col < COLS) marks[cursor_row*COLS + cursor_col] <= 1'b1;
      {was_row, was_col, was_on} <= {cursor_row, cursor_col, cursor_on};
    end
    if (mark_all) marks <= {ROWS*COLS{1'b1}};
  end

  // Running the operations
  always @(posedge clk) begin
    pop <= 1'b0;
    we  <= 1'b0;
    w_carry  <= 1'b0;
    w_mark   <= 1'b1;
    scrolled <= 1'b0;
    mark_all <= 1'b0;
    case (state)
      IDLE:
        if (!empty && !pop) begin
          pop <= 1'b1;
          case (e_op)
            TEXT_ON: begin
              text_mode <= 1'b1; cursor_on <= 1'b0; reverse <= 1'b0; top <= 0; bottom <= LAST_ROW; offset <= 0;
              cursor_row <= 0; cursor_col <= 0; mark_all <= 1'b1;
              start(1'b1, 1'b1, 0, LAST_ROW, 0, LAST_COL, ROWS);
            end
            TEXT_OFF: text_mode <= 1'b0;
            GOTO: begin
              cursor_row <= e_a > LAST_ROW ? LAST_ROW : e_a[4:0];
              cursor_col <= e_b > COLS ? COLS : e_b[4:0];
            end
            PUT:
              if (e_a >= 8'h20) begin
                if (cursor_col < COLS) begin
                  we <= 1'b1; w_row <= cursor_row; w_col <= cursor_col; w_cell <= {reverse, e_a};
                  if (cursor_col == LAST_COL && cursor_row < LAST_ROW) begin
                    cursor_row <= cursor_row + 1'b1; cursor_col <= 0;
                  end else cursor_col <= cursor_col + 1'b1;
                end
              end else if (e_a == BS) begin
                if (cursor_col != 0) cursor_col <= cursor_col - 1'b1;
              end else if (e_a == LF) begin
                if (cursor_row < LAST_ROW) cursor_row <= cursor_row + 1'b1;
                cursor_col <= 0;
              end else if (e_a == CR) cursor_col <= 0;
            CLEAR: begin
              cursor_row <= 0; cursor_col <= 0;
              start(1'b1, 1'b1, 0, LAST_ROW, 0, LAST_COL, ROWS);
            end
            CLEAR_EOL: if (cursor_col < COLS) start(1'b0, 1'b1, cursor_row, cursor_row, cursor_col, LAST_COL, COLS);
            INSERT:    if (cursor_col < COLS) start(1'b0, 1'b0, cursor_row, cursor_row, cursor_col, LAST_COL, e_a);
            DELETE:    if (cursor_col < COLS) start(1'b0, 1'b1, cursor_row, cursor_row, cursor_col, LAST_COL, e_a);
            REGION:
              if (e_a < (e_b > LAST_ROW ? LAST_ROW : e_b)) set_region(e_a[4:0], e_b > LAST_ROW ? LAST_ROW : e_b[4:0]);
            REGION_RESET: set_region(0, LAST_ROW);
            SCROLL_UP:   scroll(1'b1, top, e_a);
            SCROLL_DOWN: scroll(1'b0, top, e_a);
            INSERT_LINES, DELETE_LINES:
              if (cursor_row >= top && cursor_row <= bottom) begin
                cursor_col <= 0;
                scroll(e_op == DELETE_LINES, cursor_row, e_a);
              end
            CURSOR: cursor_on <= e_a != 0;
            VIDEO:  reverse <= e_a != 0;
          endcase
        end
      MOVE:                        // the source is being read; or a blank goes in
        if (src_ok) state <= MOVE_WRITE;
        else begin
          we <= 1'b1; w_row <= row; w_col <= col; w_cell <= BLANK; w_carry <= carry;
          step;
          if (last) finish;
        end
      MOVE_WRITE: begin
        we <= 1'b1; w_row <= row; w_col <= col; w_cell <= r_cell;
        w_carry <= carry; w_mark <= marks[src_row*COLS + src_col];
        step;
        if (last) finish; else state <= MOVE;
      end
      default: state <= IDLE;
    endcase
  end
  // The next cell of the block, in order
  task step;
    if (forward) begin
      if (col == c1) begin col <= c0; row <= row + 1'b1; end else col <= col + 1'b1;
    end else begin
      if (col == c0) begin col <= c1; row <= row - 1'b1; end else col <= col - 1'b1;
    end
  endtask
endmodule
