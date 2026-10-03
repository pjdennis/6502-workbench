// Michael writing its VIA as firmware/lib/graphics/graphics_display.inc does, with that code's cycle
// timings at 2 MHz. Include inside a testbench module that declares `reg [7:0] portb`, `reg e, csb, rstb,
// dc`, `localparam real CPU_NS` and a task `expect_byte(input [7:0] b, input d)`, which the model calls
// as each byte's E strobe rises while the display is selected.
  task cycles(input integer n); #(n * CPU_NS); endtask

  task gd_configure;   begin cycles(8); e = 1'b0; cycles(8); {rstb, csb} = 2'b11; end endtask
  task gd_reset;       begin cycles(6); rstb = 1'b0; cycles(40); rstb = 1'b1; cycles(40); end endtask
  task gd_select;      begin cycles(11); dc = 1'b1; cycles(8); csb = 1'b0; cycles(10); end endtask
  task gd_unselect;    begin cycles(11); csb = 1'b1; cycles(8); dc = 1'b0; cycles(10); end endtask

  // jsr gd_send_data: sta PORTB / lda #GD_E / tsb GD_PORT / trb GD_PORT / rts
  task gd_send_data(input [7:0] b);
    begin
      cycles(6 + 4); portb = b;
      cycles(2 + 6); if (!csb) expect_byte(b, dc); e = 1'b1;
      cycles(6);     e = 1'b0;
      cycles(6);
    end
  endtask

  // gd_send_command: DC low for one byte, high again after E has fallen
  task gd_send_command(input [7:0] b);
    begin cycles(3 + 2 + 6); dc = 1'b0; cycles(4); gd_send_data(b); cycles(2 + 6); dc = 1'b1; cycles(6); end
  endtask

  // send_zero_data's unrolled loop: sta PORTA,Y (E high) / stx PORTA (E low), one byte every 9 cycles
  task fast_fill(input [7:0] b, input integer n);
    integer i;
    begin
      cycles(4); portb = b;
      for (i = 0; i < n; i = i + 1) begin
        cycles(5); expect_byte(b, dc); e = 1'b1;
        cycles(4); e = 1'b0;
      end
    end
  endtask
