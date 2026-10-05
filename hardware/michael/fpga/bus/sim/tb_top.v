`timescale 1ns / 1ps
`include "tb_util.vh"
`include "../../rtl/cmod_a7.vh"

// The Michael FPGA bus design with the display: Michael (fpga_bus.inc's timings, the display driver's fill
// loop, and the keyboard driver's interrupt), the board between (michael_board.vh: no net with two drivers),
// an ILI9341 model on the display pins (ili9341_model.vh: every byte, its DC and the SPI timing), and the
// PC on the serial port.
module tb_top;
  localparam real CPU_NS = 500.0;  // one 65C02 cycle at 2 MHz
  localparam CPB = `CLKS_PER_BIT(`PC_BAUD);   // as on the board

  reg clk;
  `TB_CLOCK(clk, 41.667, 200_000_000)  // 12 MHz

  `include "../../sim/michael_board.vh"
  wire host_tx, fpga_tx;
  wire lcd_cs, lcd_reset, lcd_dc, lcd_mosi, lcd_sck, lcd_led, t_clk, t_cs, t_din;
  wire [1:0] led;

  top #(.ACTIVITY_CYCLES(100)) dut (
    .sysclk(clk), .d(d_pins), .e(e), .rs(rs), .rw(rw), .soeb(soeb), .pio9(1'b0), .pio10(1'b0), .backlight_tie(1'b1),
    .d_oeb(d_oeb), .d_dir(d_dir), .uart_txd_in(host_tx), .uart_rxd_out(fpga_tx),
    .lcd_cs(lcd_cs), .lcd_reset(lcd_reset), .lcd_dc(lcd_dc), .lcd_mosi(lcd_mosi), .lcd_sck(lcd_sck),
    .lcd_led(lcd_led), .t_clk(t_clk), .t_cs(t_cs), .t_din(t_din), .led(led));

  `include "../../sim/michael_fpga_bus.vh"
  `include "../../sim/host_serial.vh"
  `include "../../sim/ili9341_model.vh"

  // A display command as gd_send_command will send it: DISP_COMMAND, then the command as its argument. Each
  // byte is expected before it's sent, since the display can have it before Michael's routine returns.
  task disp_command(input [7:0] c); begin fb_command(8'h11); expect_byte(c, 1'b0); fb_data(c); end endtask
  task disp_data(input [7:0] b);    begin expect_byte(b, 1'b1); fb_data(b); end endtask
  task send_line(input [8*16-1:0] text);   // up to 16 characters, then LF
    integer k;
    begin
      for (k = 15; k >= 0; k = k - 1) if (text[8*k +: 8] != 0) send_host(text[8*k +: 8]);
      send_host(8'h0A);
    end
  endtask
  reg [7:0] got;
  task expect_status(input [7:0] exp, input [8*40-1:0] what);
    begin fb_status(got); `CHECK_EQ(got, exp, what) end
  endtask

  integer i;
  initial begin
    #2000;
    `CHECK_EQ({lcd_cs, lcd_reset, lcd_led}, 3'b111, "idle: deselected, out of reset, backlight on")
    `CHECK_EQ({t_cs, t_clk, t_din}, 3'b100, "touch controller idle")

    // ID: the raw display and text mode; GEOMETRY: text mode's rows and columns
    fb_command(8'h03); fb_command(8'h01);
    fb_read(got); `CHECK_EQ(got, "M", "ID 1") fb_read(got); `CHECK_EQ(got, "B", "ID 2")
    fb_read(got); `CHECK_EQ(got, 8'd1, "ID version") fb_read(got); `CHECK_EQ(got, 8'h03, "ID: raw display and text")
    fb_command(8'h30);
    fb_read(got); `CHECK_EQ(got, 8'd20, "GEOMETRY rows") fb_read(got); `CHECK_EQ(got, 8'd20, "GEOMETRY columns")

    // gd_reset: RESET low, then high
    fb_command(8'h10); fb_data(8'h00);
    cycles(20); `CHECK_EQ(lcd_reset, 1'b0, "display held in reset")
    fb_command(8'h10); fb_data(8'h01);
    cycles(20); `CHECK_EQ(lcd_reset, 1'b1, "display reset released")

    // Commands with parameters, as gd_initialize and the drawing routines send them
    disp_command(8'h2A); disp_data(8'h00); disp_data(8'h00); disp_data(8'h01); disp_data(8'h3F);
    disp_command(8'h36); disp_data(8'hE8);

    // A fill at the driver's full speed, with a keyboard interrupt in the middle of one strobe
    disp_command(8'h2C);
    for (i = 0; i < 48; i = i + 1) expect_byte(8'h00, 1'b1);
    kbd_byte = 8'h3C;
    fb_fill(8'h00, 48, 20);
    cycles(10);
    expect_all_received;
    expect_status(8'h00, "status after the fill: nothing lost");

    // Backlight
    fb_command(8'h13); fb_data(8'h00); cycles(20);
    `CHECK_EQ(lcd_led, 1'b0, "backlight off")
    fb_command(8'h13); fb_data(8'hFF); cycles(20);
    `CHECK_EQ(lcd_led, 1'b1, "backlight on")

    // SERIAL_SEND reaches the PC
    fb_command(8'h50); fb_data("O"); fb_data("K"); fb_data(8'h0D); fb_data(8'h0A);
    expect_line({"OK"}, "SERIAL_SEND line");

    // The debug port: the PC sends the same transactions as text lines (letters and hex in either case)
    expect_byte(8'h2A, 1'b0); expect_byte(8'h00, 1'b1); expect_byte(8'hEF, 1'b1);
    send_line("C11"); send_line("D2A 00 ef");   // DISP_COMMAND $2A, then two data bytes
    cycles(40);
    expect_all_received;
    send_line("S");
    expect_line({"s00"}, "debug status read");
    send_line("C04"); send_line("D41 42 43");   // ECHO three bytes
    send_line("R3");
    expect_line({"r414243"}, "debug read of three reply bytes");
    send_line("r");
    expect_line({"r00"}, "debug read with the reply queue empty");
    send_line("s");
    expect_line({"s08"}, "UNDERFLOW, through the debug port");
    send_line("C7F"); send_line("S");
    expect_line({"s02"}, "UNKNOWN, through the debug port");
    expect_all_received;

    // DISP_RESET ends text mode, so a graphics program started after a text one has the display: the reset
    // reaches it even while the renderer is drawing, and from then on only Michael's bytes do
    unchecked = 1'b1;                          // the renderer's bytes
    fb_command(8'h20);                         // TEXT_ON: the renderer sets up, waits a frame, draws every cell
    cycles(1000);
    for (i = 0; i < 400 && !(lcd_reset && !lcd_cs); i = i + 1) cycles(1000);
    `CHECK_EQ(lcd_cs, 1'b0, "the renderer drawing")
    expect_status(8'h80, "status in text mode: busy drawing");
    fb_command(8'h10); fb_data(8'h00);
    for (i = 0; i < 100 && lcd_reset; i = i + 1) cycles(100);
    `CHECK_EQ(lcd_reset, 1'b0, "DISP_RESET in text mode: display held in reset")
    unchecked = 1'b0;
    fb_command(8'h10); fb_data(8'h01);
    disp_command(8'h36); disp_data(8'hE8);
    cycles(2000);
    expect_all_received;
    expect_status(8'h00, "status after DISP_RESET in text mode: nothing refused, nothing busy");
    `TB_PASS
  end
endmodule
