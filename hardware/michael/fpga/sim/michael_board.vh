// The board between Michael and the FPGA bus: the VIA's port B, the keyboard board (driving port B while SOEB
// is low) and the data buffer (a 74LVC245 controlled by d_oeb and d_dir, its A side on d_pins), with checks
// that no net ever has two drivers, that the buffer turns round only while it's off, and that reads turn the
// bus round in time. Include in a testbench module before the design, instantiated as `dut` with its D pins on
// d_pins and its drive enable named d_drive; then include michael_fpga_bus.vh for Michael.
  reg        e = 1'b0, rs = 1'b0, rw = 1'b0, soeb = 1'b1, via_drive = 1'b0;
  reg  [7:0] via_out = 8'h00, kbd_byte = 8'h00;
  wire [7:0] portb, d_pins;
  wire       d_oeb, d_dir;
  wire       buf_to_michael = !d_oeb && d_dir, buf_to_fpga = !d_oeb && !d_dir;

  assign portb  = via_drive      ? via_out  : 8'bz;
  assign portb  = !soeb          ? kbd_byte : 8'bz;
  assign portb  = buf_to_michael ? d_pins   : 8'bz;
  assign d_pins = buf_to_fpga    ? portb    : 8'bz;

  // No two drivers on a net. Checked 1 ns after any change: the parts switch in zero time here, and the
  // real ones take a few ns.
  wire fpga_drives = dut.d_drive;
  always @(via_drive, soeb, buf_to_michael, buf_to_fpga, fpga_drives) #1 begin
    `CHECK(via_drive + !soeb + buf_to_michael <= 1, "two drivers on port B")
    `CHECK(buf_to_fpga + fpga_drives <= 1, "two drivers on the D pins")
  end
  always @(d_dir) if ($time > 0) `CHECK_EQ(d_oeb, 1'b1, "DIR changed while the buffer was on")

  // Reads: the byte reaches port B within 1 us of E rising, and the bus is released within 1 us of E
  // falling (unless the keyboard board took port B first)
  realtime t_e_rise = 0, t_e_fall = 0, t_drive = 0;
  always @(posedge buf_to_michael) begin   // the read's first drive: later ones follow a keyboard interrupt
    if (t_drive < t_e_rise) `CHECK($realtime - t_e_rise <= 1000.0, "byte on port B more than 1 us after E rose")
    t_drive = $realtime;
  end
  always @(negedge buf_to_michael) if (!e)
    `CHECK($realtime - t_e_fall <= 1000.0, "port B released more than 1 us after E fell")

