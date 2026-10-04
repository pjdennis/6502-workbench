`timescale 1ns / 1ps
// The Michael FPGA bus's debug port: the PC makes the same transactions as Michael, as text lines on the
// Cmod's USB serial port (letters and hex digits in either case; spaces ignored; lines end with LF or CR):
//   C hh hh ...   write command bytes                  R [n]   read n bytes (1 if no n) of the reply queue;
//   D hh hh ...   write data bytes                             answers "r" and the bytes in hex
//                                                     S       read the status byte; answers "s" and it in hex
// Answers end with CR LF. Transactions wait for a clock without one of Michael's (bus_busy), and each answer
// character for a clock when out_ready is high: out_valid follows it in the same clock, so nothing collides.
// Characters arriving while an answer is going out are dropped, so the PC waits for each answer.
module debug_port (
  input            clk,
  input            rx_valid,      // characters from the PC
  input      [7:0] rx_data,
  input            bus_busy,      // Michael's transfer this clock
  output reg       wr = 1'b0,     // transactions, as michael_bus.v makes them
  output reg       wr_rs = 1'b0,
  output reg [7:0] wr_data = 8'h00,
  output reg       rd = 1'b0,
  output reg       rd_end = 1'b0,
  output reg       rd_rs = 1'b0,
  input      [7:0] reply_byte,
  input      [7:0] status_byte,
  output           out_valid,     // characters for the PC
  output     [7:0] out_data,
  input            out_ready
);
  localparam IDLE = 4'd0, WRITE = 4'd1, READ_ARG = 4'd2, STATUS_ARG = 4'd3, SKIP = 4'd4, HEAD = 4'd5,
             READ = 4'd6, READ_END = 4'd7, HIGH = 4'd8, LOW = 4'd9, CR = 4'd10, LF = 4'd11;
  reg [3:0] state = IDLE;
  reg       write_rs = 1'b0, have_nibble = 1'b0, have_count = 1'b0, pending = 1'b0;
  reg [3:0] nibble = 4'h0;
  reg [7:0] count = 8'h00, value = 8'h00, pending_byte = 8'h00;

  function [4:0] hex_value(input [7:0] c);   // {valid, value}
    hex_value = c >= "0" && c <= "9" ? {1'b1, c[3:0]} :
                (c >= "A" && c <= "F") || (c >= "a" && c <= "f") ? {1'b1, c[3:0] + 4'd9} : 5'b0;
  endfunction
  function [7:0] hex_char(input [3:0] n); hex_char = n < 10 ? "0" + n : "A" + n - 10; endfunction
  wire [4:0] hex = hex_value(rx_data);
  wire       eol = rx_data == 8'h0A || rx_data == 8'h0D;

  // The answer's characters, one in each of these states
  assign out_valid = out_ready && (state == HEAD || state == HIGH || state == LOW || state == CR || state == LF);
  assign out_data  = state == HEAD ? (rd_rs ? "r" : "s") : state == HIGH ? hex_char(value[7:4]) :
                     state == LOW ? hex_char(value[3:0]) : state == CR ? 8'h0D : 8'h0A;

  always @(posedge clk) begin
    wr        <= 1'b0;
    rd        <= 1'b0;
    rd_end    <= 1'b0;
    if (pending && !bus_busy) begin   // a write, waiting for a clock of its own
      wr      <= 1'b1;
      wr_rs   <= write_rs;
      wr_data <= pending_byte;
      pending <= 1'b0;
    end
    case (state)
      IDLE:
        if (rx_valid)
          case (rx_data)
            "C", "c": begin write_rs <= 1'b0; have_nibble <= 1'b0; state <= WRITE; end
            "D", "d": begin write_rs <= 1'b1; have_nibble <= 1'b0; state <= WRITE; end
            "R", "r": begin count <= 8'd0; have_count <= 1'b0; rd_rs <= 1'b1; state <= READ_ARG; end
            "S", "s": begin count <= 8'd1; rd_rs <= 1'b0; state <= STATUS_ARG; end
            " ", 8'h0A, 8'h0D: ;
            default: state <= SKIP;
          endcase
      WRITE:
        if (rx_valid) begin
          if (hex[4]) begin
            if (have_nibble) begin pending <= 1'b1; pending_byte <= {nibble, hex[3:0]}; end
            nibble      <= hex[3:0];
            have_nibble <= !have_nibble;
          end else if (eol) state <= IDLE;
          else if (rx_data != " ") state <= SKIP;
        end
      READ_ARG:
        if (rx_valid) begin
          if (hex[4]) begin count <= {count[3:0], hex[3:0]}; have_count <= 1'b1; end
          else if (eol) begin if (!have_count) count <= 8'd1; state <= HEAD; end
          else if (rx_data != " ") state <= SKIP;
        end
      STATUS_ARG:
        if (rx_valid) begin
          if (eol) state <= READ;   // read first, so the answer isn't counted in BUSY
          else if (rx_data != " ") state <= SKIP;
        end
      SKIP:
        if (rx_valid && eol) state <= IDLE;
      HEAD:     if (out_ready) state <= !rd_rs ? HIGH : count == 0 ? CR : READ;
      READ:
        if (!bus_busy) begin
          value <= rd_rs ? reply_byte : status_byte;
          rd    <= 1'b1;
          state <= READ_END;
        end
      READ_END:
        if (!bus_busy) begin rd_end <= 1'b1; count <= count - 1'b1; state <= rd_rs ? HIGH : HEAD; end
      HIGH:     if (out_ready) state <= LOW;
      LOW:      if (out_ready) state <= count == 0 ? CR : READ;
      CR:       if (out_ready) state <= LF;
      LF:       if (out_ready) state <= IDLE;
      default:  state <= IDLE;
    endcase
  end
endmodule
