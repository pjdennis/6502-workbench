// An ILI9341 on the display pins (4-wire SPI, mode 0, MSB first), checking each byte it receives, with its DC
// level, against the bytes a testbench expects, and the SPI timing against the ILI9341's limits. Include in a
// testbench module with wires lcd_cs, lcd_reset, lcd_dc, lcd_mosi and lcd_sck. The testbench calls
// expect_byte(byte, dc) for each byte the display should receive, in order, and expect_all_received to check
// that they all arrived.
  reg [7:0] exp_byte [0:4095];
  reg       exp_dc   [0:4095];
  integer   n_exp = 0;
  task expect_byte(input [7:0] b, input d);
    begin exp_byte[n_exp] = b; exp_dc[n_exp] = d; n_exp = n_exp + 1; end
  endtask

  integer n_rx = 0, bits = 0;
  reg [7:0] sr;
  reg dc_first;
  realtime last_rise = -1.0e9, mosi_change = -1.0e9, cs_fall = -1.0e9;

  always @(lcd_mosi) mosi_change = $realtime;
  always @(negedge lcd_cs) cs_fall = $realtime;
  always @(negedge lcd_reset) bits = 0;  // a hardware reset abandons a partial byte
  always @(posedge lcd_cs) if (lcd_reset) `CHECK_EQ(bits, 0, "CS released in the middle of a byte")

  always @(posedge lcd_sck) if (lcd_reset) begin
    `CHECK_EQ(lcd_cs, 1'b0, "SCK pulse while CS is high")
    `CHECK($realtime - last_rise >= 100.0, "SCK faster than the ILI9341's 100 ns write cycle")
    `CHECK($realtime - mosi_change >= 30.0, "MOSI setup before SCK under 30 ns")
    `CHECK($realtime - cs_fall >= 40.0, "CS to first SCK under 40 ns")
    if (bits == 0) dc_first = lcd_dc;
    else `CHECK_EQ(lcd_dc, dc_first, "DC changed within a byte")
    sr = {sr[6:0], lcd_mosi};
    bits = bits + 1;
    if (bits == 8) begin
      `CHECK(n_rx < n_exp, "display received a byte nobody sent")
      `CHECK_EQ(sr, exp_byte[n_rx], "byte received by the display")
      `CHECK_EQ(dc_first, exp_dc[n_rx], "DC of the byte received by the display")
      n_rx = n_rx + 1;
      bits = 0;
    end
    last_rise = $realtime;
  end

  task expect_all_received;
    begin #5000; `CHECK_EQ(n_rx, n_exp, "bytes received by the display") end
  endtask

