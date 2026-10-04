`timescale 1ns / 1ps
// The Michael FPGA bus's command layer (docs/michael-fpga-bus-plan.md, "Commands"), fed by michael_bus.v:
// the control commands ($0x), the reply queue, the status byte, and SERIAL_SEND ($50, provisional), whose
// data bytes go to the PC through the Cmod's USB serial port.
//
// A byte with RS 0 is a command and always starts a new one. Bytes with RS 1 are data: a command's
// arguments, then, for a streaming command, any number of data bytes. Errors set sticky status bits,
// which a status read reports and clears.
module bus_control #(
  parameter       REPLY_DEPTH  = 512,
  parameter [7:0] CAPABILITIES = 8'h00   // the ID reply's capabilities byte
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
  output reg [7:0] ser_data = 8'h00
);
  localparam [7:0] NOP = 8'h00, ID = 8'h01, RESET = 8'h03, ECHO = 8'h04, SERIAL_SEND = 8'h50;
  localparam [7:0] VERSION = 8'd1;
  localparam ABANDONED = 0, UNKNOWN = 1, EXTRA = 2, UNDERFLOW = 3, OVERFLOW = 4;

  function known(input [7:0] c);
    known = c == NOP || c == ID || c == RESET || c == ECHO || c == SERIAL_SEND;
  endfunction
  function streams(input [7:0] c);
    streams = c == ECHO || c == SERIAL_SEND;
  endfunction
  function [2:0] arguments(input [7:0] c);   // none of these commands has arguments yet
    arguments = 3'd0;
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
    if (push && full)           sticky[OVERFLOW]  <= 1'b1;
    if (rd && rd_rs && empty)   sticky[UNDERFLOW] <= 1'b1;

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
