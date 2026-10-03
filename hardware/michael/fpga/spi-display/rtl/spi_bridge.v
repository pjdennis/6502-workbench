`timescale 1ns / 1ps
// Michael's parallel display writes to ILI9341 SPI (4-wire, mode 0, MSB first, SCK = clk / 2).
//
// Michael writes a byte to VIA port B, then pulses E (PA0) high. On each rising edge of E while the
// display is selected (CSB low), the byte and DC are latched and shifted out. RSTB goes straight to the
// display's RESET and also abandons any byte in progress. CS stays low while Michael selects the display
// and until the last byte has been shifted out.
//
// At 12 MHz a byte takes 16 clocks plus 2 to 3 for synchronising E: about 1.5 us. Michael's fastest
// loop sends a byte every 4.5 us, so a byte is always finished before the next strobe.
module spi_bridge (
  input            clk,
  input      [7:0] d,          // VIA port B; stable around the E strobe
  input            e,          // asynchronous inputs from Michael
  input            csb,
  input            rstb,
  input            dc,
  output           selected,   // Michael has the display selected
  output           accepted,   // pulses for one clock when a byte is latched
  output           lcd_cs,
  output           lcd_reset,
  output reg       lcd_dc = 1'b0,
  output           lcd_mosi,
  output reg       lcd_sck = 1'b0
);
  reg [2:0] e_sync = 3'b000;  // two synchroniser stages and one for edge detection
  reg [1:0] csb_sync = 2'b11, rstb_sync = 2'b11;
  always @(posedge clk) begin
    e_sync    <= {e_sync[1:0], e};
    csb_sync  <= {csb_sync[0], csb};
    rstb_sync <= {rstb_sync[0], rstb};
  end

  reg [7:0] shift = 8'h00;
  reg [3:0] bits_left = 0;
  wire busy = bits_left != 0;

  wire in_reset = !rstb_sync[1];
  assign selected = !csb_sync[1];
  assign accepted = e_sync[1] && !e_sync[2] && selected && !in_reset && bits_left == 0;

  always @(posedge clk)
    if (in_reset) begin
      bits_left <= 0;
      lcd_sck   <= 1'b0;
    end else if (accepted) begin
      shift     <= d;
      lcd_dc    <= dc;
      bits_left <= 8;
    end else if (busy) begin
      lcd_sck <= !lcd_sck;
      if (lcd_sck) begin  // falling SCK: present the next bit
        shift     <= {shift[6:0], 1'b0};
        bits_left <= bits_left - 1'b1;
      end
    end

  assign lcd_mosi  = shift[7];
  assign lcd_cs    = !(selected || busy);
  assign lcd_reset = !in_reset;
endmodule
