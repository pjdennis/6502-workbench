`timescale 1ns / 1ps
// Michael's parallel display writes to ILI9341 SPI (4-wire, mode 0, MSB first, SCK = clk / 2).
//
// Michael writes a byte to VIA port B, then pulses E (PA0) high. On each rising edge of E while the
// display is selected (CSB low), the byte and DC are latched and shifted out. RSTB goes straight to the
// display's RESET and also abandons any byte in progress. CS stays low while Michael selects the display
// and until the last byte has been shifted out.
//
// E is filtered (level_filter.v): a level counts once it has held for 3 clocks (250 ns), so spikes on E
// from switching noise aren't strobes. Michael's strobes are high for 2 us or more. The byte and DC are
// still taken at E's first high sample.
//
// At 12 MHz a byte takes 16 clocks plus about 5 for synchronising and filtering E: under 2 us. Michael's
// fastest loop sends a byte every 4.5 us, so a byte is always finished before the next strobe.
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
  reg [1:0] e_sync = 2'b00, csb_sync = 2'b11, rstb_sync = 2'b11;
  reg [8:0] d_dc_sync1 = 0, d_dc_sync2 = 0, d_dc_at_e = 0;   // {d, dc}, synchronised with E, and as E rose
  reg       e_prev = 1'b0;
  wire      e_f, e_starting;
  level_filter e_filter (.clk(clk), .in(e_sync[1]), .level(e_f), .glitch(), .starting(e_starting));
  always @(posedge clk) begin
    e_sync     <= {e_sync[0], e};
    d_dc_sync1 <= {d, dc};
    d_dc_sync2 <= d_dc_sync1;
    if (e_starting && e_sync[1]) d_dc_at_e <= d_dc_sync2;
    e_prev     <= e_f;
    csb_sync   <= {csb_sync[0], csb};
    rstb_sync  <= {rstb_sync[0], rstb};
  end

  reg [7:0] shift = 8'h00;
  reg [3:0] bits_left = 0;
  wire busy = bits_left != 0;

  wire in_reset = !rstb_sync[1];
  assign selected = !csb_sync[1];
  assign accepted = e_f && !e_prev && selected && !in_reset && bits_left == 0;

  always @(posedge clk)
    if (in_reset) begin
      bits_left <= 0;
      lcd_sck   <= 1'b0;
    end else if (accepted) begin
      shift     <= d_dc_at_e[8:1];
      lcd_dc    <= d_dc_at_e[0];
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
