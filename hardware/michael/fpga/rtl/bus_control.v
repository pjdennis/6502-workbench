`timescale 1ns / 1ps
// The Michael FPGA bus's command layer (docs/michael-fpga-bus-plan.md, "Commands"), fed by michael_bus.v:
// the control commands ($0x), the reply queue, the status byte, SERIAL_SEND ($50, provisional), whose data
// bytes go to the PC through the Cmod's USB serial port, and, with DISPLAY, the raw display commands ($1x),
// whose effects go to a display queue (display_spi.v) as entries: kind and value.
//
// A byte with RS 0 is a command and always starts a new one. Bytes with RS 1 are data: a command's
// arguments, then, for a streaming command, any number of data bytes. Errors set sticky status bits,
// which a status read reports and clears.
module bus_control #(
  parameter       REPLY_DEPTH  = 512,
  parameter       DISPLAY      = 0       // 1: the raw display commands (and capabilities bit 0)
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
  input            disp_full
);
  localparam [7:0] NOP = 8'h00, ID = 8'h01, RESET = 8'h03, ECHO = 8'h04, SERIAL_SEND = 8'h50,
                   DISP_RESET = 8'h10, DISP_COMMAND = 8'h11, DISP_DATA = 8'h12, BACKLIGHT = 8'h13;
  localparam [7:0] VERSION = 8'd1, CAPABILITIES = DISPLAY ? 8'h01 : 8'h00;
  localparam ABANDONED = 0, UNKNOWN = 1, EXTRA = 2, UNDERFLOW = 3, OVERFLOW = 4;
  localparam [1:0] D_DATA = 2'd0, D_COMMAND = 2'd1, D_RESET = 2'd2, D_BACKLIGHT = 2'd3;   // display_spi.v's

  function display(input [7:0] c);
    display = DISPLAY && (c == DISP_RESET || c == DISP_COMMAND || c == DISP_DATA || c == BACKLIGHT);
  endfunction
  function known(input [7:0] c);
    known = c == NOP || c == ID || c == RESET || c == ECHO || c == SERIAL_SEND || display(c);
  endfunction
  function streams(input [7:0] c);
    streams = c == ECHO || c == SERIAL_SEND || c == DISP_COMMAND || c == DISP_DATA;
  endfunction
  function [2:0] arguments(input [7:0] c);
    arguments = display(c) && c != DISP_DATA ? 3'd1 : 3'd0;
  endfunction

  reg  [7:0] cmd = NOP;
  reg  [2:0] args_left = 3'd0;
  reg  [4:0] sticky = 5'd0;
  assign status_byte = {busy, 2'b00, sticky};

  // The ID reply goes in a byte a clock
  reg  [2:0] id_left = 3'd0;
  wire [7:0] id_byte = id_left == 4 ? "M" : id_left == 3 ? "B" : id_left == 2 ? VERSION : CAPABILITIES;

  wire is_command = wr && !wr_rs;
  wire is_data    = wr && wr_rs;
  wire echo       = is_data && args_left == 0 && cmd == ECHO;
  wire push       = echo || (id_left != 0);
  wire reset      = is_command && wr_data == RESET;

  // The display: a display command's argument is an entry of its own (the ILI9341 command, the reset level
  // or the brightness); the data bytes of DISP_COMMAND and DISP_DATA are DATA entries
  assign disp_push  = is_data && display(cmd) && (args_left == 1 || (args_left == 0 && streams(cmd)));
  assign disp_kind  = args_left == 0 ? D_DATA : cmd == DISP_COMMAND ? D_COMMAND : cmd == DISP_RESET ? D_RESET :
                      D_BACKLIGHT;
  assign disp_value = wr_data;

  // The reply queue
  wire [7:0] head;
  wire       empty, full;
  fifo #(.WIDTH(8), .DEPTH(REPLY_DEPTH)) replies (
    .clk(clk), .clear(reset), .push(push), .din(echo ? wr_data : id_byte), .full(full),
    .pop(rd_end && rd_rs), .dout(head), .empty(empty), .count());
  assign reply_byte = empty ? 8'h00 : head;

  always @(posedge clk) begin
    ser_valid <= 1'b0;
    if (!echo && id_left != 0) id_left <= id_left - 1'b1;

    // Status: a status read clears what it reports; errors from this clock are kept
    if (rd && !rd_rs) sticky <= 5'd0;
    if (reset) begin
      sticky  <= 5'd0;
      id_left <= 3'd0;
    end
    if ((push && full) || (disp_push && disp_full)) sticky[OVERFLOW] <= 1'b1;
    if (rd && rd_rs && empty) sticky[UNDERFLOW] <= 1'b1;

    if (is_command) begin
      if (args_left != 0) sticky[ABANDONED] <= 1'b1;
      if (!known(wr_data)) sticky[UNKNOWN] <= 1'b1;
      cmd       <= wr_data;
      args_left <= arguments(wr_data);
      if (wr_data == ID) id_left <= 3'd4;
    end else if (is_data) begin
      if (args_left != 0)
        args_left <= args_left - 1'b1;
      else if (cmd == SERIAL_SEND) begin
        ser_valid <= 1'b1;
        ser_data  <= wr_data;
      end else if (known(cmd) && !streams(cmd))
        sticky[EXTRA] <= 1'b1;   // an unknown command's data is ignored silently
    end
  end
endmodule
