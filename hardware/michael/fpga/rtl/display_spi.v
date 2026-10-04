`timescale 1ns / 1ps
// The ILI9341 display, fed from a queue (4-wire SPI, mode 0, MSB first, SCK = clk / 2: 6 MHz at 12 MHz).
// Entries are taken in order:
//   DATA       the byte, with DC high          RESET      the display's RESET line to value[0]
//   COMMAND    the byte, with DC low           BACKLIGHT  the brightness, 0 (off) to 255 (fully on), by PWM
// CS is low while a byte is going out, and rises between bytes. The ILI9341 allows that anywhere between whole
// bytes, even within a command's parameters or a RAMWR's pixels: it carries on from where it paused (its data
// sheet's "Data Transfer Pause"). Only a break in the middle of a byte makes it drop that byte, and this
// never makes one. Reads would need CS held low across the command and the reply, but this design doesn't
// read. On the board, Michael's streams have always gone this way, a byte per CS pulse.
// The backlight starts fully on. Its PWM edges disturb the SPI lines on the board (they made snow on the
// display), so it changes only while CS is high, and the next byte waits GUARD clocks after a change, for
// the lines to settle.
module display_spi #(
  parameter QUEUE_DEPTH = 512,
  parameter GUARD       = 12   // 1 us at 12 MHz
) (
  input            clk,
  input            push,
  input      [1:0] kind,
  input      [7:0] value,
  output           full,
  output           busy,       // entries waiting, or a byte going out
  output           lcd_cs,
  output reg       lcd_reset = 1'b1,
  output reg       lcd_dc = 1'b1,
  output           lcd_mosi,
  output reg       lcd_sck = 1'b0,
  output reg       lcd_led = 1'b1
);
  localparam DATA = 2'd0, COMMAND = 2'd1, RESET = 2'd2, BACKLIGHT = 2'd3;

  wire [9:0] entry;
  wire       empty;
  reg  [3:0] bits_left = 0;
  wire       shifting = bits_left != 0;
  reg  [7:0] shift = 8'h00, brightness = 8'hFF, pwm = 8'h00;
  reg  [$clog2(GUARD + 1)-1:0] guard = 0;
  wire       led = brightness == 8'hFF || pwm < brightness;   // the backlight as the PWM has it
  wire       led_change = led != lcd_led && !shifting;
  wire       take = !empty && !shifting && !led_change && guard == 0;
  fifo #(.WIDTH(10), .DEPTH(QUEUE_DEPTH)) entries (
    .clk(clk), .clear(1'b0), .push(push), .din({kind, value}), .full(full), .pop(take), .dout(entry),
    .empty(empty), .count());
  assign busy     = !empty || shifting;
  assign lcd_cs   = !shifting;
  assign lcd_mosi = shift[7];

  always @(posedge clk) begin
    pwm <= pwm + 1'b1;
    if (led_change) begin lcd_led <= led; guard <= GUARD; end
    else if (guard != 0) guard <= guard - 1'b1;
    if (take)
      case (entry[9:8])
        DATA, COMMAND: begin shift <= entry[7:0]; lcd_dc <= entry[9:8] == DATA; bits_left <= 8; end
        RESET:         lcd_reset <= entry[0];
        BACKLIGHT:     brightness <= entry[7:0];
      endcase
    else if (shifting) begin
      lcd_sck <= !lcd_sck;
      if (lcd_sck) begin   // falling SCK: present the next bit
        shift     <= {shift[6:0], 1'b0};
        bits_left <= bits_left - 1'b1;
      end
    end
  end
endmodule
