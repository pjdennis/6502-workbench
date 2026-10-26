// A W5500 on the net pins (SPI mode 0, MSB first; docs/michael-fpga-w5500-plan.md), as the emulator's
// chips/w5500.c has it: a frame is two address bytes, a control byte (the block in bits 7-3, write in bit 2, the
// mode in bits 1-0: 0 variable length, until CS rises; 1, 2 or 3 fixed at 1, 2 or 4 data bytes) and data, the
// address counting up. While the header goes in, MISO answers $01, $02, $03. Registers: the first 256 bytes of
// each block; VERSIONR ($0039) reads $04 and can't be written; MR's RST (bit 7) resets them; so does RSTn low,
// which also ignores the bus. Include in a testbench module with wires net_sclk, net_mosi, net_cs_n and
// net_rst_n; it drives net_miso (high-impedance while deselected: the testbench adds a pull-up) and net_int_n.
// w5500_restart starts the frame again as a glitch on CS would. It checks the SPI against its limits.
  reg  [7:0] w5500_mem [0:8191];   // {block, address[7:0]}
  reg        w5500_miso = 1'b1, w5500_driving = 1'b0, w5500_int_n = 1'b1;
  assign net_miso  = w5500_driving ? w5500_miso : 1'bz;
  assign net_int_n = w5500_int_n;
  integer    w5500_bits = 0, w5500_phase = 0, w5500_left = 0, w5500_frames = 0, w5500_sclk_while_reset = 0;
  reg  [7:0] w5500_in = 8'h00, w5500_out = 8'h00, w5500_ctl = 8'h00;
  reg [15:0] w5500_addr = 16'h0000;
  realtime   w5500_rise = -1.0e9, w5500_fall = -1.0e9, w5500_mosi_at = -1.0e9, w5500_cs_at = -1.0e9;

  task w5500_reset_registers;
    integer i;
    begin
      for (i = 0; i < 8192; i = i + 1) w5500_mem[i] = 8'h00;
      w5500_mem[16'h19] = 8'h07; w5500_mem[16'h1A] = 8'hD0;   // RTR
      w5500_mem[16'h1B] = 8'h08;                              // RCR
      w5500_mem[16'h2E] = 8'hBF;                              // PHYCFGR: link up, 100 Mbps, full duplex
      w5500_mem[16'h39] = 8'h04;                              // VERSIONR
    end
  endtask
  initial w5500_reset_registers;

  task w5500_restart;
    begin w5500_bits = 0; w5500_phase = 0; w5500_out = 8'h01; w5500_miso = 1'b0; end
  endtask

  function [12:0] w5500_cell(input [7:0] ctl, input [15:0] addr);
    w5500_cell = {ctl[7:3], addr[7:0]};
  endfunction

  always @(negedge net_rst_n) w5500_reset_registers;
  always @(net_mosi) w5500_mosi_at = $realtime;
  always @(negedge net_cs_n) begin
    w5500_cs_at = $realtime;
    if (net_rst_n) begin w5500_driving = 1'b1; w5500_restart; end
  end
  always @(posedge net_cs_n) begin
    w5500_driving = 1'b0;
    if (net_rst_n) `CHECK_EQ(w5500_bits, 0, "the W5500's CS rose in the middle of a byte")
  end

  always @(posedge net_sclk) begin
    if (!net_rst_n && !net_cs_n) w5500_sclk_while_reset = w5500_sclk_while_reset + 1;
    if (net_rst_n && !net_cs_n) begin
      `CHECK($realtime - w5500_fall >= 6.0, "W5500 SCLK low under 6 ns")
      `CHECK($realtime - w5500_mosi_at >= 5.0, "W5500 MOSI setup under 5 ns")
      `CHECK($realtime - w5500_cs_at >= 5.0, "W5500 CS to first SCLK under 5 ns")
      w5500_in   = {w5500_in[6:0], net_mosi};
      w5500_bits = w5500_bits + 1;
      if (w5500_bits == 8) begin
        w5500_bits = 0;
        case (w5500_phase)
          0: begin w5500_addr[15:8] = w5500_in; w5500_out = 8'h02; w5500_phase = 1; end
          1: begin w5500_addr[7:0] = w5500_in; w5500_out = 8'h03; w5500_phase = 2; end
          2: begin
            w5500_ctl    = w5500_in;
            w5500_left   = w5500_in[1:0] == 2'd0 ? -1 : w5500_in[1:0] == 2'd3 ? 4 : w5500_in[1:0];
            w5500_out    = w5500_in[2] ? 8'h00 : w5500_mem[w5500_cell(w5500_ctl, w5500_addr)];
            w5500_phase  = 3;
            w5500_frames = w5500_frames + 1;
          end
          default: begin
            if (w5500_ctl[2]) begin
              if (w5500_ctl[7:3] == 0 && w5500_addr == 16'h0000 && w5500_in[7]) w5500_reset_registers;
              else if (!(w5500_ctl[7:3] == 0 && w5500_addr == 16'h0039))
                w5500_mem[w5500_cell(w5500_ctl, w5500_addr)] = w5500_in;
            end
            w5500_addr = w5500_addr + 1'b1;
            w5500_out  = w5500_ctl[2] ? 8'h00 : w5500_mem[w5500_cell(w5500_ctl, w5500_addr)];
            if (w5500_left > 0) begin
              w5500_left = w5500_left - 1;
              if (w5500_left == 0) begin w5500_phase = 0; w5500_out = 8'h01; end   // fixed length: the next frame
            end
          end
        endcase
      end
    end
    w5500_rise = $realtime;
  end

  // MISO changes as SCLK falls: the next bit of the byte going out
  always @(negedge net_sclk) begin
    if (net_rst_n && !net_cs_n) begin
      `CHECK($realtime - w5500_rise >= 6.0, "W5500 SCLK high under 6 ns")
      w5500_miso = w5500_out[7 - w5500_bits];
    end
    w5500_fall = $realtime;
  end
