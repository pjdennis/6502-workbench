`timescale 1ns / 1ps
`include "tb_util.vh"

// net_spi.v against the W5500 model: RSTn held low after configuration, then high; a read of VERSIONR ($04);
// a write read back in another frame; a 256-byte read (count 0); bytes read wait for rx_take; a frame whose
// header isn't answered $01 $02 $03 is reported; RESET pulses RSTn and resets the W5500; SCLK never runs while
// CS is high, nor CS rises inside a byte (the model checks).
module tb_net_spi;
  reg clk;
  `TB_CLOCK(clk, 41.667, 20_000_000)  // 12 MHz

  localparam RESET_CYCLES = 50, RESET_WAIT = 30;
  localparam [2:0] RESET = 3'd0, HEADER = 3'd1, DATA = 3'd2, READ = 3'd3, END = 3'd4;
  reg        push = 1'b0, rx_take = 1'b0;
  reg  [2:0] kind = RESET;
  reg  [7:0] value = 8'h00;
  wire       full, busy, rx_valid, header_error, frame_open, net_cs_n, net_sclk, net_mosi, net_miso, net_rst_n,
             net_int_n;
  wire [7:0] rx_data;
  pullup (net_miso);
  net_spi #(.QUEUE_DEPTH(16), .RESET_CYCLES(RESET_CYCLES), .RESET_WAIT(RESET_WAIT)) dut (
    .clk(clk), .push(push), .kind(kind), .value(value), .full(full), .busy(busy),
    .rx_valid(rx_valid), .rx_data(rx_data), .rx_take(rx_take), .header_error(header_error),
    .frame_open(frame_open), .net_cs_n(net_cs_n), .net_sclk(net_sclk), .net_mosi(net_mosi), .net_miso(net_miso),
    .net_rst_n(net_rst_n));

  `include "../sim/w5500_model.vh"

  integer header_errors = 0, sclk_while_deselected = 0;
  always @(posedge clk) if (header_error) header_errors = header_errors + 1;
  always @(posedge net_sclk) if (net_cs_n) sclk_while_deselected = sclk_while_deselected + 1;

  task queue(input [2:0] k, input [7:0] v);
    begin kind = k; value = v; push = 1'b1; @(posedge clk); #1 push = 1'b0; end
  endtask
  task header(input [15:0] addr, input [7:0] control);
    begin queue(HEADER, addr[15:8]); queue(HEADER, addr[7:0]); queue(HEADER, control); end
  endtask
  task wait_idle; begin while (busy) @(posedge clk); #1; end endtask

  // Bytes read, taken as they come (or held back while take_late is set)
  reg  [7:0] got [0:511];
  integer    n_got = 0;
  reg        take_late = 1'b0;
  always @(posedge clk) begin
    rx_take <= 1'b0;
    if (rx_valid && !rx_take && !take_late) begin got[n_got] = rx_data; n_got = n_got + 1; rx_take <= 1'b1; end
  end

  integer i;
  initial begin
    // After configuration: RSTn low, then high, and busy until the W5500 has had RESET_WAIT more
    #1;
    `CHECK_EQ(net_rst_n, 1'b0, "RSTn low after configuration")
    `CHECK_EQ(net_cs_n, 1'b1, "deselected after configuration")
    `CHECK(busy, "busy while the W5500 resets")
    repeat (RESET_CYCLES) @(posedge clk);
    #1 `CHECK_EQ(net_rst_n, 1'b1, "RSTn released")
    `CHECK(busy, "busy while the W5500 starts")
    wait_idle;

    // VERSIONR, one byte
    header(16'h0039, 8'h00);
    queue(READ, 8'd1);
    wait_idle;
    `CHECK_EQ(n_got, 1, "one byte read")
    `CHECK_EQ(got[0], 8'h04, "VERSIONR")
    `CHECK_EQ(net_cs_n, 1'b1, "a read's frame ends")
    `CHECK_EQ(w5500_frames, 1, "one frame")

    // A write, then a read back in a frame of its own
    header(16'h0001, 8'h04);
    queue(DATA, 8'd192); queue(DATA, 8'd168); queue(DATA, 8'd8); queue(DATA, 8'd1);
    wait_idle;
    `CHECK(frame_open, "a write's frame stays open until END")
    queue(END, 8'h00);
    wait_idle;
    `CHECK(!frame_open && net_cs_n, "END closes the frame")
    header(16'h0001, 8'h00);
    queue(READ, 8'd4);
    wait_idle;
    `CHECK_EQ({got[1], got[2], got[3], got[4]}, {8'd192, 8'd168, 8'd8, 8'd1}, "the gateway, read back")

    // A count of 0 reads 256 bytes, held back until taken
    n_got = 0;
    take_late = 1'b1;
    header(16'h0000, 8'h00);
    queue(READ, 8'd0);
    repeat (200) @(posedge clk);
    `CHECK(rx_valid, "a byte waits to be taken")
    `CHECK(busy, "busy while it waits")
    take_late = 1'b0;
    wait_idle;
    `CHECK_EQ(n_got, 256, "count 0 reads 256 bytes")
    `CHECK_EQ(got[16'h39], 8'h04, "VERSIONR among them")
    `CHECK_EQ(header_errors, 0, "headers answered $01 $02 $03")

    // A glitch during the header: the W5500 starts again, and the frame is reported
    queue(HEADER, 8'h00);
    wait_idle;
    w5500_restart;
    queue(HEADER, 8'h39); queue(HEADER, 8'h00); queue(READ, 8'd1);
    wait_idle;
    `CHECK_EQ(header_errors, 1, "a frame the W5500 didn't take whole")

    // RESET: RSTn low, the registers back to their reset values
    queue(RESET, 8'h00);
    @(posedge clk); #1 `CHECK_EQ(net_rst_n, 1'b0, "RESET pulls RSTn low (taken the clock after it was queued)")
    wait_idle;
    `CHECK_EQ(net_rst_n, 1'b1, "and releases it")
    n_got = 0;
    header(16'h0001, 8'h00);
    queue(READ, 8'd1);
    wait_idle;
    `CHECK_EQ(got[0], 8'h00, "the gateway reset")

    `CHECK_EQ(sclk_while_deselected, 0, "SCLK while deselected")
    `CHECK_EQ(w5500_sclk_while_reset, 0, "SCLK while in reset")
    `TB_PASS
  end
endmodule
