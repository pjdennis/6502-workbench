`timescale 1ns / 1ps
// The Michael FPGA bus's command layer (docs/michael-fpga-bus-plan.md, "Commands"), fed by michael_bus.v:
// the control commands ($0x), the reply queue, the status byte, SERIAL_SEND ($50, provisional), whose data
// bytes go to the PC through the Cmod's USB serial port, and, with DISPLAY, the raw display commands ($1x),
// whose effects go to a display queue (display_spi.v) as entries: kind and value. With TEXT, text mode, the
// first long-form device ($80: its first data byte is the operation): operations $00-$0F go to the text grid
// (text_grid.v) as operations with their arguments, PUT's data a character each, and GEOMETRY ($10) replies
// the grid's rows and columns. Internally a command is 9 bits: a long form's operation is {1, operation}, a
// one-byte command {0, command}. Between TEXT_ON and TEXT_OFF the text renderer has the display: DISP_COMMAND and DISP_DATA are
// refused (UNKNOWN). DISP_RESET ends text mode (with a TEXT_OFF to the grid), as a reset loses all the
// renderer set up, so a graphics program, which starts with one, has the display. text_mode follows at once,
// so the renderer stops before the reset's entry, not when the grid gets to its TEXT_OFF.
//
// A byte with RS 0 is a command and always starts a new one. Bytes with RS 1 are data: a command's
// arguments (a long form's operation first), then, for a streaming command, any number of data bytes. Errors set sticky status bits,
// which a status read reports and clears.
module bus_control #(
  parameter       REPLY_DEPTH  = 512,
  parameter       DISPLAY      = 0,      // 1: the raw display commands (and capabilities bit 0)
  parameter       TEXT         = 0,      // 1: text mode (and capabilities bit 1)
  parameter [7:0] TEXT_ROWS    = 20,
  parameter [7:0] TEXT_COLS    = 20
) (
  input        clk,
  input        wr,
  input        wr_rs,
  input  [7:0] wr_data,
  input        rd,
  input        rd_end,
  input        rd_rs,
  output [7:0] reply_byte,   // the head of the reply queue ($00 when it's empty)
  output [7:0] status_byte,
  input        busy,         // status bit 7: devices still working through what they were sent
  output reg       ser_valid = 1'b0,  // SERIAL_SEND's bytes, one clock each
  output reg [7:0] ser_data = 8'h00,
  output           disp_push,         // a display queue entry (display_spi.v's kinds)
  output     [1:0] disp_kind,
  output     [7:0] disp_value,
  input            disp_full,
  output           text_push,         // a text grid operation
  output     [3:0] text_op,
  output     [7:0] text_a,
  output     [7:0] text_b,
  input            text_full,
  output reg       text_mode = 1'b0
);
  localparam [8:0] NOP = 9'h000, ID = 9'h001, RESET = 9'h003, ECHO = 9'h004, SERIAL_SEND = 9'h050,
                   DISP_RESET = 9'h010, DISP_COMMAND = 9'h011, DISP_DATA = 9'h012, BACKLIGHT = 9'h013,
                   TEXT_DEVICE = 9'h080,
                   TEXT_ON = 9'h100, TEXT_OFF = 9'h101, GOTO = 9'h102, PUT = 9'h103, CLEAR = 9'h104,
                   CLEAR_EOL = 9'h105, REGION = 9'h108, REGION_RESET = 9'h109, GEOMETRY = 9'h110;
  localparam [7:0] VERSION = 8'd2, CAPABILITIES = {6'd0, TEXT != 0, DISPLAY != 0};
  localparam ABANDONED = 0, UNKNOWN = 1, EXTRA = 2, UNDERFLOW = 3, OVERFLOW = 4;
  localparam [1:0] D_DATA = 2'd0, D_COMMAND = 2'd1, D_RESET = 2'd2, D_BACKLIGHT = 2'd3;   // display_spi.v's

  // (The functions take all they use as arguments: simulation re-evaluates a function in a continuous
  // assignment only when its arguments change)
  function display(input [8:0] c, input text_mode);   // in text mode, BACKLIGHT and DISP_RESET
    display = DISPLAY && (c == BACKLIGHT || c == DISP_RESET || (!text_mode && (c == DISP_COMMAND || c == DISP_DATA)));
  endfunction
  function text(input [8:0] c);      // an operation for the text grid
    text = TEXT && c >= TEXT_ON && c < GEOMETRY;
  endfunction
  function known(input [8:0] c, input text_mode);
    known = c == NOP || c == ID || c == RESET || c == ECHO || c == SERIAL_SEND || display(c, text_mode) || text(c) ||
            (TEXT && (c == TEXT_DEVICE || c == GEOMETRY));
  endfunction
  function streams(input [8:0] c);
    streams = c == ECHO || c == SERIAL_SEND || c == DISP_COMMAND || c == DISP_DATA || (TEXT && c == PUT);
  endfunction
  // Arguments: a long-form device's 1 (its operation); GOTO and REGION 2; TEXT_ON to VIDEO without data 0; the rest 1
  function [2:0] arguments(input [8:0] c, input text_mode);
    arguments = display(c, text_mode) && c != DISP_DATA ? 3'd1 :
                TEXT && c == TEXT_DEVICE ? 3'd1 :
                !text(c) || c == PUT ? 3'd0 :
                c == GOTO || c == REGION ? 3'd2 :
                c == TEXT_ON || c == TEXT_OFF || c == CLEAR || c == CLEAR_EOL || c == REGION_RESET ? 3'd0 : 3'd1;
  endfunction

  reg  [8:0] cmd = NOP;
  reg  [2:0] args_left = 3'd0;
  reg  [4:0] sticky = 5'd0;
  assign status_byte = {busy, 2'b00, sticky};

  // The ID reply goes in a byte a clock, as does GEOMETRY's
  reg  [2:0] id_left = 3'd0, geo_left = 3'd0;
  wire [7:0] id_byte = geo_left == 2 ? TEXT_ROWS : geo_left == 1 ? TEXT_COLS :
                       id_left == 4 ? "M" : id_left == 3 ? "B" : id_left == 2 ? VERSION : CAPABILITIES;

  wire is_command = wr && !wr_rs;
  wire is_data    = wr && wr_rs;
  wire [8:0] command = {1'b0, wr_data};
  wire is_op      = is_data && TEXT && cmd == TEXT_DEVICE;   // a long form's operation (args_left is 1)
  wire [8:0] op   = {1'b1, wr_data};
  wire echo       = is_data && args_left == 0 && cmd == ECHO;
  wire push       = echo || id_left != 0 || geo_left != 0;
  wire reset      = is_command && command == RESET;

  // The display: a display command's argument is an entry of its own (the ILI9341 command, the reset level
  // or the brightness); the data bytes of DISP_COMMAND and DISP_DATA are DATA entries
  assign disp_push  = is_data && display(cmd, text_mode) && (args_left == 1 || (args_left == 0 && streams(cmd)));
  assign disp_kind  = args_left == 0 ? D_DATA : cmd == DISP_COMMAND ? D_COMMAND : cmd == DISP_RESET ? D_RESET :
                      D_BACKLIGHT;
  assign disp_value = wr_data;

  // The text grid: an operation when the operation arrives (without arguments), with its last argument, or
  // for each of PUT's characters; and a TEXT_OFF for DISP_RESET
  reg  [7:0] first_arg = 8'h00;
  wire disp_reset = TEXT && text_mode && is_command && command == DISP_RESET;
  wire bare_op    = is_op && text(op) && arguments(op, text_mode) == 0 && op != PUT;
  assign text_push = bare_op || (is_data && text(cmd) && (args_left == 1 || (args_left == 0 && cmd == PUT))) ||
                     disp_reset;
  wire [8:0] op_cmd = disp_reset ? TEXT_OFF : is_op ? op : cmd;
  assign text_op = op_cmd[3:0];
  assign text_a  = disp_reset || is_op ? 8'h00 : arguments(cmd, text_mode) == 2 ? first_arg : wr_data;
  assign text_b  = disp_reset || is_op || arguments(cmd, text_mode) != 2 ? 8'h00 : wr_data;

  // The reply queue
  wire [7:0] head;
  wire       empty, full;
  fifo #(.WIDTH(8), .DEPTH(REPLY_DEPTH)) replies (
    .clk(clk), .clear(reset), .push(push), .din(echo ? wr_data : id_byte), .full(full),
    .pop(rd_end && rd_rs), .dout(head), .empty(empty), .count());
  assign reply_byte = empty ? 8'h00 : head;

  always @(posedge clk) begin
    ser_valid <= 1'b0;
    if (!echo && geo_left != 0) geo_left <= geo_left - 1'b1;
    else if (!echo && id_left != 0) id_left <= id_left - 1'b1;

    // Status: a status read clears what it reports; errors from this clock are kept
    if (rd && !rd_rs) sticky <= 5'd0;
    if (reset) begin
      sticky  <= 5'd0;
      id_left <= 3'd0;
      geo_left <= 3'd0;
    end
    if ((push && full) || (disp_push && disp_full) || (text_push && text_full)) sticky[OVERFLOW] <= 1'b1;
    if (rd && rd_rs && empty) sticky[UNDERFLOW] <= 1'b1;

    if (is_command) begin
      if (args_left != 0) sticky[ABANDONED] <= 1'b1;
      if (!known(command, text_mode)) sticky[UNKNOWN] <= 1'b1;
      cmd       <= command;
      args_left <= arguments(command, text_mode);
      if (command == ID) id_left <= 3'd4;
      if (TEXT && command == DISP_RESET) text_mode <= 1'b0;
    end else if (is_op) begin    // an unknown operation's data is ignored silently
      if (!known(op, text_mode)) sticky[UNKNOWN] <= 1'b1;
      cmd       <= op;
      args_left <= arguments(op, text_mode);
      if (op == GEOMETRY) geo_left <= 3'd2;
      if (op == TEXT_ON) text_mode <= 1'b1;
      if (op == TEXT_OFF) text_mode <= 1'b0;
    end else if (is_data) begin
      if (args_left != 0) begin
        args_left <= args_left - 1'b1;
        if (args_left == 2) first_arg <= wr_data;
      end
      else if (cmd == SERIAL_SEND) begin
        ser_valid <= 1'b1;
        ser_data  <= wr_data;
      end else if (known(cmd, text_mode) && !streams(cmd))
        sticky[EXTRA] <= 1'b1;   // an unknown command's data is ignored silently
    end
  end
endmodule
