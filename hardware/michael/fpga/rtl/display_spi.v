`timescale 1ns / 1ps
// The ILI9341 display, fed from a queue (4-wire SPI, mode 0, MSB first, SCK = clk / 2: 6 MHz at 12 MHz).
// Entries are taken in order:
//   DATA       the byte, with DC high          RESET      the display's RESET line to value[0]
//   COMMAND    the byte, with DC low           BACKLIGHT  the brightness, 0 (off) to 255 (fully on), by PWM
// CS is low while entries are waiting or a byte is going out. The backlight starts fully on.
module display_spi #(
  parameter QUEUE_DEPTH = 512
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
  output           lcd_led
);
  localparam DATA = 2'd0, COMMAND = 2'd1, RESET = 2'd2, BACKLIGHT = 2'd3;

  wire [9:0] entry;
  wire       empty;
  reg  [3:0] bits_left = 0;
  wire       shifting = bits_left != 0;
  wire       take = !empty && !shifting;
  fifo #(.WIDTH(10), .DEPTH(QUEUE_DEPTH)) entries (
    .clk(clk), .clear(1'b0), .push(push), .din({kind, value}), .full(full), .pop(take), .dout(entry),
    .empty(empty), .count());
  assign busy   = !empty || shifting;
  assign lcd_cs = !busy;

  reg [7:0] shift = 8'h00, brightness = 8'hFF, pwm = 8'h00;
  assign lcd_mosi = shift[7];
  assign lcd_led  = brightness == 8'hFF || pwm < brightness;

  always @(posedge clk) begin
    pwm <= pwm + 1'b1;
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
