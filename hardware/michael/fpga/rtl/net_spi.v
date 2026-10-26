`timescale 1ns / 1ps
// The W5500 Ethernet controller's SPI (docs/michael-fpga-w5500-plan.md): mode 0, MSB first, SCLK = clk /
// (2 * HALF), 6 MHz at 12 MHz with HALF 1; fed from a queue of entries, as display_spi.v is. Entries, in order:
//   RESET   RSTn low for RESET_CYCLES, then RESET_WAIT more before anything else (the W5500's PLL), as after
//           configuration
//   HEADER  a byte of a frame's header (the address's two bytes, then the control byte); the first opens the
//           frame (CS low, CS_GAP clocks before the first SCLK)
//   DATA    a byte written
//   READ    value bytes read (0 means 256), then the frame ends
//   END     the frame ends (CS high CS_GAP clocks after the last SCLK)
// While the header goes out the W5500 answers $01 $02 $03; a frame that gets anything else pulses header_error
// once (its bytes still come). Bytes read come out on rx_data with rx_valid, until rx_take takes each; the next
// waits for it. Entries without a frame open (DATA, READ, END) are dropped.
module net_spi #(
  parameter QUEUE_DEPTH  = 512,
  parameter HALF         = 1,        // clocks per SCLK half period
  parameter CS_GAP       = 2,        // clocks between a CS edge and the nearest SCLK edge
  parameter RESET_CYCLES = 12_000,   // 1 ms at 12 MHz
  parameter RESET_WAIT   = 24_000    // 2 ms
) (
  input            clk,
  input            push,
  input      [2:0] kind,
  input      [7:0] value,
  output           full,
  output           busy,          // entries waiting, a byte or a reset under way, or a byte read not yet taken
  output reg       rx_valid = 1'b0,
  output reg [7:0] rx_data = 8'h00,
  input            rx_take,
  output reg       header_error = 1'b0,
  output reg       frame_open = 1'b0,
  output reg       net_cs_n = 1'b1,
  output reg       net_sclk = 1'b0,
  output           net_mosi,
  input            net_miso,
  output reg       net_rst_n = 1'b0
);
  localparam [2:0] RESET = 3'd0, HEADER = 3'd1, DATA = 3'd2, READ = 3'd3, END = 3'd4;
  localparam [2:0] S_IDLE = 3'd0, S_RESET = 3'd1, S_OPEN = 3'd2, S_BYTE = 3'd3, S_TAKE = 3'd4, S_CLOSE = 3'd5;
  localparam TW = $clog2(RESET_CYCLES + RESET_WAIT + 1);

  reg  [2:0]    state = S_RESET;
  reg  [TW-1:0] timer = RESET_CYCLES + RESET_WAIT;
  reg  [7:0]    tx = 8'h00, rx = 8'h00;
  reg  [3:0]    bits = 4'd0;              // bits left in the byte
  reg  [$clog2(HALF + 1)-1:0] half = 0;
  reg  [2:0]    byte_kind = DATA;         // HEADER, DATA or READ
  reg  [1:0]    header_n = 2'd0;          // header bytes sent in this frame
  reg           header_bad = 1'b0;
  reg  [8:0]    read_left = 9'd0;

  wire          empty;
  wire [10:0]   entry;
  wire          take = state == S_IDLE && !empty;
  fifo #(.WIDTH(11), .DEPTH(QUEUE_DEPTH)) entries (
    .clk(clk), .clear(1'b0), .push(push), .din({kind, value}), .full(full), .pop(take), .dout(entry),
    .empty(empty), .count());
  wire [2:0]    k = entry[10:8];
  wire [7:0]    v = entry[7:0];

  assign busy     = !empty || state != S_IDLE;
  assign net_mosi = tx[7];

  task start_byte(input [2:0] what, input [7:0] b);
    begin tx <= b; byte_kind <= what; bits <= 4'd8; half <= HALF - 1; state <= S_BYTE; end
  endtask

  always @(posedge clk) begin
    header_error <= 1'b0;
    if (rx_take) rx_valid <= 1'b0;
    case (state)
      S_RESET: begin
        if (timer == RESET_WAIT + 1) net_rst_n <= 1'b1;   // low for RESET_CYCLES clocks
        if (timer == 0) state <= S_IDLE;
        else timer <= timer - 1'b1;
      end
      S_IDLE: if (take)
        case (k)
          RESET: begin
            net_cs_n <= 1'b1; frame_open <= 1'b0; net_rst_n <= 1'b0;
            timer <= RESET_CYCLES + RESET_WAIT; state <= S_RESET;
          end
          HEADER:
            if (frame_open) start_byte(HEADER, v);
            else begin
              net_cs_n <= 1'b0; frame_open <= 1'b1; header_n <= 2'd0; header_bad <= 1'b0;
              tx <= v; timer <= CS_GAP; state <= S_OPEN;
            end
          DATA: if (frame_open) start_byte(DATA, v);
          READ: if (frame_open) begin read_left <= v == 0 ? 9'd256 : {1'b0, v}; start_byte(READ, 8'h00); end
          END:  if (frame_open) begin timer <= CS_GAP; state <= S_CLOSE; end
          default: ;
        endcase
      S_OPEN: if (timer == 0) start_byte(HEADER, tx); else timer <= timer - 1'b1;
      S_BYTE:
        if (half != 0) half <= half - 1'b1;
        else begin
          half     <= HALF - 1;
          net_sclk <= !net_sclk;
          if (!net_sclk) rx <= {rx[6:0], net_miso};      // rising: sample MISO (the W5500 changed it at the fall)
          else if (bits != 1) begin                       // falling: the next bit
            tx   <= {tx[6:0], 1'b0};
            bits <= bits - 1'b1;
          end else begin                                  // the byte's done
            bits <= 4'd0;
            case (byte_kind)
              HEADER: begin
                if (rx != {6'd0, header_n + 1'b1} && !header_bad) begin header_bad <= 1'b1; header_error <= 1'b1; end
                header_n <= header_n + 1'b1;
                state    <= S_IDLE;
              end
              READ: begin rx_data <= rx; rx_valid <= 1'b1; read_left <= read_left - 1'b1; state <= S_TAKE; end
              default: state <= S_IDLE;
            endcase
          end
        end
      S_TAKE: if (!rx_valid || rx_take) begin
        if (read_left != 0) start_byte(READ, 8'h00);
        else begin timer <= CS_GAP; state <= S_CLOSE; end
      end
      S_CLOSE: if (timer == 0) begin net_cs_n <= 1'b1; frame_open <= 1'b0; state <= S_IDLE; end
               else timer <= timer - 1'b1;
      default: state <= S_IDLE;
    endcase
  end
endmodule
