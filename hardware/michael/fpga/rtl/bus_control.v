`timescale 1ns / 1ps
// The Michael FPGA bus's command layer (docs/michael-fpga-bus-plan.md, "Commands"), fed by michael_bus.v:
// the control commands ($0x), the reply queue, the status byte, SERIAL_SEND ($50, provisional), whose data
// bytes go to the PC through the Cmod's USB serial port, and, with DISPLAY, the raw display commands ($1x),
// whose effects go to a display queue (display_spi.v) as entries: kind and value. With TEXT, text mode, the
// first long-form device ($80: its first data byte is the operation): operations $00-$0F go to the text grid
// (text_grid.v) as operations with their arguments, PUT's data a character each, and GEOMETRY ($10) replies
// the grid's rows and columns. Internally a command is 10 bits, the device above the byte: a one-byte command
// {00, command}, a text mode operation {01, operation}, a network operation {10, operation}. Between TEXT_ON and TEXT_OFF the text renderer has the display: DISP_COMMAND and DISP_DATA are
// refused (UNKNOWN). DISP_RESET ends text mode (with a TEXT_OFF to the grid), as a reset loses all the
// renderer set up, so a graphics program, which starts with one, has the display. text_mode follows at once,
// so the renderer stops before the reset's entry, not when the grid gets to its TEXT_OFF.
//
// With NET, the network, the long-form device $81 (docs/michael-fpga-w5500-plan.md), for net_spi.v and the W5500:
// NET_RESET ($00) a RESET entry; NET_READ ($01: address high, address low, control byte, count) three HEADER
// entries and a READ, the bytes read joining the reply queue as net_spi.v offers them; NET_WRITE ($02: address,
// control byte, then data) three HEADER entries and a DATA entry for each data byte, the frame ending (an END
// entry) at the next command, as does a NET_READ cut short; NET_STATUS ($03) replies {INTn low, a frame open} in
// bits 0 and 1. A frame whose header the W5500 didn't answer $01 $02 $03 sets NET_ERROR (status bit 5).
//
// A byte with RS 0 is a command and always starts a new one. Bytes with RS 1 are data: a command's
// arguments (a long form's operation first), then, for a streaming command, any number of data bytes. Errors set sticky status bits,
// which a status read reports and clears.
module bus_control #(
  parameter       REPLY_DEPTH  = 512,
  parameter       DISPLAY      = 0,      // 1: the raw display commands (and capabilities bit 0)
  parameter       TEXT         = 0,      // 1: text mode (and capabilities bit 1)
  parameter       NET          = 0,      // 1: the network (and capabilities bit 3)
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
  output reg       text_mode = 1'b0,
  output           net_push,          // an entry for net_spi.v
  output     [2:0] net_kind,
  output     [7:0] net_value,
  input            net_full,
  input            net_rx_valid,      // a byte net_spi.v read, taken by net_rx_take
  input      [7:0] net_rx_data,
  output           net_rx_take,
  input            net_header_error,
  input            net_frame_open,
  input            net_int_n
);
  localparam [9:0] NOP = 10'h000, ID = 10'h001, RESET = 10'h003, ECHO = 10'h004, SERIAL_SEND = 10'h050,
                   DISP_RESET = 10'h010, DISP_COMMAND = 10'h011, DISP_DATA = 10'h012, BACKLIGHT = 10'h013,
                   TEXT_DEVICE = 10'h080,
                   TEXT_ON = 10'h100, TEXT_OFF = 10'h101, GOTO = 10'h102, PUT = 10'h103, CLEAR = 10'h104,
                   CLEAR_EOL = 10'h105, REGION = 10'h108, REGION_RESET = 10'h109, GEOMETRY = 10'h110,
                   NET_DEVICE = 10'h081,
                   NET_RESET = 10'h200, NET_READ = 10'h201, NET_WRITE = 10'h202, NET_STATUS = 10'h203;
  localparam [7:0] VERSION = 8'd2, CAPABILITIES = {4'd0, NET != 0, 1'b0, TEXT != 0, DISPLAY != 0};
  localparam ABANDONED = 0, UNKNOWN = 1, EXTRA = 2, UNDERFLOW = 3, OVERFLOW = 4, NET_ERROR = 5;
  localparam [2:0] N_RESET = 3'd0, N_HEADER = 3'd1, N_DATA = 3'd2, N_READ = 3'd3, N_END = 3'd4;   // net_spi.v's
  localparam [1:0] D_DATA = 2'd0, D_COMMAND = 2'd1, D_RESET = 2'd2, D_BACKLIGHT = 2'd3;   // display_spi.v's

  // (The functions take all they use as arguments: simulation re-evaluates a function in a continuous
  // assignment only when its arguments change)
  function display(input [9:0] c, input text_mode);   // in text mode, BACKLIGHT and DISP_RESET
    display = DISPLAY && (c == BACKLIGHT || c == DISP_RESET || (!text_mode && (c == DISP_COMMAND || c == DISP_DATA)));
  endfunction
  function text(input [9:0] c);      // an operation for the text grid
    text = TEXT && c >= TEXT_ON && c < GEOMETRY;
  endfunction
  function net(input [9:0] c);       // a network operation
    net = NET && c >= NET_RESET && c <= NET_STATUS;
  endfunction
  function known(input [9:0] c, input text_mode);
    known = c == NOP || c == ID || c == RESET || c == ECHO || c == SERIAL_SEND || display(c, text_mode) || text(c) ||
            (TEXT && (c == TEXT_DEVICE || c == GEOMETRY)) || net(c) || (NET && c == NET_DEVICE);
  endfunction
  function streams(input [9:0] c);
    streams = c == ECHO || c == SERIAL_SEND || c == DISP_COMMAND || c == DISP_DATA || (TEXT && c == PUT) ||
              (NET && c == NET_WRITE);
  endfunction
  // Arguments: a long-form device's 1 (its operation); GOTO and REGION 2; TEXT_ON to VIDEO without data 0; the rest 1
  function [2:0] arguments(input [9:0] c, input text_mode);
    arguments = display(c, text_mode) && c != DISP_DATA ? 3'd1 :
                TEXT && c == TEXT_DEVICE ? 3'd1 :
                NET && c == NET_DEVICE ? 3'd1 :
                NET && c == NET_READ ? 3'd4 :
                NET && c == NET_WRITE ? 3'd3 :
                !text(c) || c == PUT ? 3'd0 :
                c == GOTO || c == REGION ? 3'd2 :
                c == TEXT_ON || c == TEXT_OFF || c == CLEAR || c == CLEAR_EOL || c == REGION_RESET ? 3'd0 : 3'd1;
  endfunction

  reg  [9:0] cmd = NOP;
  reg  [2:0] args_left = 3'd0;
  reg  [5:0] sticky = 6'd0;
  assign status_byte = {busy, 1'b0, sticky};

  // The ID reply goes in a byte a clock, as does GEOMETRY's
  reg  [2:0] id_left = 3'd0, geo_left = 3'd0;
  wire [7:0] id_byte = geo_left == 2 ? TEXT_ROWS : geo_left == 1 ? TEXT_COLS :
                       id_left == 4 ? "M" : id_left == 3 ? "B" : id_left == 2 ? VERSION : CAPABILITIES;

  wire is_command = wr && !wr_rs;
  wire is_data    = wr && wr_rs;
  wire [9:0] command = {2'b00, wr_data};
  wire net_op     = NET && cmd == NET_DEVICE;
  wire is_op      = is_data && ((TEXT && cmd == TEXT_DEVICE) || net_op);   // a long form's operation (args_left is 1)
  wire [9:0] op   = {net_op ? 2'b10 : 2'b01, wr_data};
  wire echo       = is_data && args_left == 0 && cmd == ECHO;
  wire net_status = is_op && op == NET_STATUS;
  wire own_push   = echo || id_left != 0 || geo_left != 0 || net_status;
  assign net_rx_take = NET && net_rx_valid && !own_push;   // the bytes the W5500 sent wait for a free clock
  wire push       = own_push || net_rx_take;
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
  wire [9:0] op_cmd = disp_reset ? TEXT_OFF : is_op ? op : cmd;
  assign text_op = op_cmd[3:0];
  assign text_a  = disp_reset || is_op ? 8'h00 : arguments(cmd, text_mode) == 2 ? first_arg : wr_data;
  assign text_b  = disp_reset || is_op || arguments(cmd, text_mode) != 2 ? 8'h00 : wr_data;

  // The network: a NET_READ's or NET_WRITE's header and NET_READ's count as their arguments arrive, NET_WRITE's
  // data, NET_RESET when the operation arrives, and an END when a command cuts a frame off
  wire net_frame_end = NET && is_command && (cmd == NET_WRITE || (cmd == NET_READ && args_left != 0));
  assign net_push  = (is_op && op == NET_RESET) || (is_data && (cmd == NET_READ || cmd == NET_WRITE) &&
                     (args_left != 0 || cmd == NET_WRITE)) || net_frame_end;
  assign net_kind  = net_frame_end ? N_END : is_op ? N_RESET : args_left == 0 ? N_DATA :
                     cmd == NET_READ && args_left == 1 ? N_READ : N_HEADER;
  assign net_value = net_frame_end || is_op ? 8'h00 : wr_data;

  // The reply queue
  wire [7:0] head;
  wire       empty, full;
  wire [7:0] reply_in = echo ? wr_data : id_left != 0 || geo_left != 0 ? id_byte :
                        net_status ? {6'd0, net_frame_open, !net_int_n} : net_rx_data;
  fifo #(.WIDTH(8), .DEPTH(REPLY_DEPTH)) replies (
    .clk(clk), .clear(reset), .push(push), .din(reply_in), .full(full),
    .pop(rd_end && rd_rs), .dout(head), .empty(empty), .count());
  assign reply_byte = empty ? 8'h00 : head;

  always @(posedge clk) begin
    ser_valid <= 1'b0;
    if (!echo && geo_left != 0) geo_left <= geo_left - 1'b1;
    else if (!echo && id_left != 0) id_left <= id_left - 1'b1;

    // Status: a status read clears what it reports; errors from this clock are kept
    if (rd && !rd_rs) sticky <= 6'd0;
    if (reset) begin
      sticky  <= 6'd0;
      id_left <= 3'd0;
      geo_left <= 3'd0;
    end
    if ((push && full) || (disp_push && disp_full) || (text_push && text_full) || (net_push && net_full))
      sticky[OVERFLOW] <= 1'b1;
    if (NET && net_header_error) sticky[NET_ERROR] <= 1'b1;
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
