`timescale 1ns / 1ps
`include "tb_util.vh"
`include "../../rtl/cmod_a7.vh"

// The host side sends display-probe commands over the serial port; an ILI9341 model on the SPI pins
// records what is written and answers reads.
module tb_display_probe;
  localparam BAUD = 3_000_000, CPB = `CLKS_PER_BIT(BAUD), LEN = 11;  // 3 Mbaud keeps the simulation short

  reg clk;
  reg host_valid = 1'b0;
  reg [7:0] host_data = 0;
  wire host_ready, host_tx, fpga_tx, rx_valid;
  wire [7:0] rx_data;
  wire lcd_cs, lcd_reset, lcd_dc, pin_mosi, pin_sck, lcd_led;
  reg  miso = 1'b1;
  wire d_oeb, d_dir;

  display_probe #(.BAUD(BAUD)) dut (
    .sysclk(clk), .d(8'h00), .e(1'b0), .csb(1'b1), .rstb(1'b1), .dc(1'b0), .bl(1'b1),
    .uart_txd_in(host_tx), .uart_rxd_out(fpga_tx),
    .lcd_cs(lcd_cs), .lcd_reset(lcd_reset), .lcd_dc(lcd_dc), .lcd_mosi(pin_mosi), .lcd_sck(pin_sck),
    .lcd_led(lcd_led), .lcd_miso(miso), .t_clk(), .t_cs(), .t_din(), .led(), .d_oeb(d_oeb), .d_dir(d_dir));

  uart_tx #(.CLKS_PER_BIT(CPB)) host_uart_tx (.clk(clk), .valid(host_valid), .data(host_data), .ready(host_ready), .tx(host_tx));
  uart_rx #(.CLKS_PER_BIT(CPB)) host_uart_rx (.clk(clk), .rx(fpga_tx), .valid(rx_valid), .data(rx_data));

  `TB_CLOCK(clk, 41.667, 50_000_000)

  // ---- ILI9341 model -------------------------------------------------------------------------------
  reg swapped = 1'b0;  // the model can be wired with MOSI and SCK the other way round
  wire sck  = swapped ? pin_mosi : pin_sck;
  wire mosi = swapped ? pin_sck : pin_mosi;
  reg [7:0] got_byte [0:255];
  reg       got_dc   [0:255];
  integer   n_got = 0, bits = 0, out_bits = 0;
  reg [7:0] sr;
  reg [24:0] reply;          // 1 dummy bit, then 24 bits
  realtime last_rise = -1.0e9, min_period = 1.0e9;

  always @(posedge lcd_cs) bits = 0;
  always @(posedge sck) if (!lcd_cs) begin
    if (last_rise > 0 && $realtime - last_rise < min_period) min_period = $realtime - last_rise;
    last_rise = $realtime;
    if (out_bits == 0) begin
      sr = {sr[6:0], mosi};
      bits = bits + 1;
      if (bits == 8) begin
        got_byte[n_got] = sr; got_dc[n_got] = lcd_dc; n_got = n_got + 1; bits = 0;
        if (!lcd_dc && sr == 8'h04) begin reply = {1'b0, 24'h123456}; out_bits = 25; end
      end
    end
  end
  always @(negedge sck) if (!lcd_cs && out_bits != 0) begin  // the display changes SDO on falling SCK
    miso = reply[out_bits - 1];
    out_bits = out_bits - 1;
  end
  always @(posedge lcd_cs) begin out_bits = 0; miso = 1'b1; end

  // ---- Host --------------------------------------------------------------------------------------
  task send(input [7:0] b);
    begin
      host_data = b; host_valid = 1;
      @(posedge clk); while (!host_ready) @(posedge clk);
      #1 host_valid = 0;
    end
  endtask

  reg [8*LEN-1:0] line = 0;
  integer n_lines = 0;
  always @(posedge clk) if (rx_valid) begin
    line = {line[8*LEN-9:0], rx_data};
    if (rx_data == 8'h0A) n_lines = n_lines + 1;
  end

  task expect_reply(input [8*LEN-1:0] exp);
    integer lines_before, waited;
    begin
      lines_before = n_lines;
      for (waited = 0; n_lines == lines_before && waited < 2000; waited = waited + 1) #1000;
      if (line !== exp) begin
        $display("got \"%s\", expected \"%s\"", line[8*LEN-1:16], exp[8*LEN-1:16]);
        `CHECK(0, "reply line")
      end
    end
  endtask

  task sync; begin send(8'h06); expect_reply({"K00000000", 8'h0D, 8'h0A}); end endtask

  // control byte: bit 0 CS, 1 DC, 2 RESET, 3 backlight, 4 swap MOSI/SCK
  task ctrl(input [4:0] v); begin send(8'h03); send({3'b000, v}); end endtask

  integer i;
  initial begin
    repeat (20) @(posedge clk);
    `CHECK_EQ({lcd_cs, lcd_reset, lcd_led}, 3'b111, "idle: deselected, out of reset, backlight on")
    `CHECK_EQ({d_oeb, d_dir}, 2'b00, "data buffer enabled, Michael to the FPGA (stage 1 of the bus plan)")
    sync;

    // Control lines follow the control byte
    ctrl(5'b01010); sync;                       // CS low, DC high, RESET low, backlight on
    `CHECK_EQ({lcd_cs, lcd_dc, lcd_reset, lcd_led}, 4'b0101, "control lines")
    ctrl(5'b01111); sync;
    `CHECK_EQ({lcd_cs, lcd_dc, lcd_reset, lcd_led}, 4'b1111, "control lines released")

    // Writes: a command (DC low) then data (DC high), at the default (slow) speed
    ctrl(5'b01100);                             // CS low, DC low
    send(8'h01); send(8'd1); send(8'h2A);       // write 1 byte
    ctrl(5'b01110);                             // DC high
    send(8'h01); send(8'd3); send(8'h00); send(8'hEF); send(8'h5A);
    ctrl(5'b01111); sync;
    `CHECK_EQ(n_got, 4, "bytes written")
    `CHECK_EQ({got_byte[0], got_dc[0]}, {8'h2A, 1'b0}, "command byte")
    `CHECK_EQ({got_byte[1], got_byte[2], got_byte[3]}, 24'h00EF5A, "data bytes")
    `CHECK_EQ({got_dc[1], got_dc[2], got_dc[3]}, 3'b111, "data DC")
    `CHECK(min_period >= 900.0, "default SCK is slow (about 1 MHz)")

    // A read: command 04 then 25 bits (1 dummy + 24) back on MISO
    ctrl(5'b01100); send(8'h01); send(8'd1); send(8'h04);
    send(8'h02); send(8'd25);
    expect_reply({"R00123456", 8'h0D, 8'h0A});
    ctrl(5'b01111);

    // Fill: 3 repeats of a byte pair, at full speed
    send(8'h04); send(8'd1);                    // SCK half period 1 clock: 6 MHz
    min_period = 1.0e9;
    ctrl(5'b01110);
    send(8'h05); send(8'd0); send(8'd0); send(8'd3); send(8'hF8); send(8'h00);
    ctrl(5'b01111); sync;
    `CHECK_EQ(n_got, 5 + 6, "fill bytes")
    for (i = 0; i < 3; i = i + 1) `CHECK_EQ({got_byte[5 + 2*i], got_byte[6 + 2*i]}, 16'hF800, "fill pattern")
    `CHECK(min_period >= 160.0 && min_period < 200.0, "fast SCK is 6 MHz")

    // Swap: with the model wired the other way round, swapped outputs still reach it correctly
    send(8'h04); send(8'd6);
    swapped = 1'b1;
    ctrl(5'b11100); send(8'h01); send(8'd1); send(8'hC3); ctrl(5'b11111); sync;
    `CHECK_EQ({got_byte[n_got - 1], got_dc[n_got - 1]}, {8'hC3, 1'b0}, "byte through swapped pins")
    `TB_PASS
  end
endmodule
