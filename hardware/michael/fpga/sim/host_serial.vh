// The PC on the Cmod's serial port: send_host(byte), and the lines received (line, n_lines) with
// expect_line(text, what). Include in a testbench module with `clk`, a localparam CPB (clocks per bit), and
// wires host_tx (to the design's uart_txd_in) and fpga_tx (from its uart_rxd_out).
  wire host_ready, rx_valid;
  wire [7:0] rx_data;
  reg  host_valid = 1'b0;
  reg  [7:0] host_data = 8'h00;
  uart_tx #(.CLKS_PER_BIT(CPB)) host_uart_tx (.clk(clk), .valid(host_valid), .data(host_data), .ready(host_ready), .tx(host_tx));
  uart_rx #(.CLKS_PER_BIT(CPB)) host_uart_rx (.clk(clk), .rx(fpga_tx), .valid(rx_valid), .data(rx_data));

  reg [8*96-1:0] line = 0;   // the latest complete line received, without CR LF
  reg [8*96-1:0] partial = 0;
  integer n_lines = 0;
  always @(posedge clk) if (rx_valid) begin
    if (rx_data == 8'h0A) begin line = partial; partial = 0; n_lines = n_lines + 1; end
    else if (rx_data != 8'h0D) partial = {partial[8*95-1:0], rx_data};
  end

  task send_host(input [7:0] b);
    begin
      host_data = b; host_valid = 1;
      @(posedge clk); while (!host_ready) @(posedge clk);
      #1 host_valid = 0;
    end
  endtask

  task expect_line(input [8*96-1:0] exp, input [8*40-1:0] what);
    integer lines_before, waited;
    begin
      lines_before = n_lines;
      for (waited = 0; n_lines == lines_before && waited < 20000; waited = waited + 1) #1000;
      if (line !== exp) $display("got \"%0s\", expected \"%0s\"", line, exp);
      `CHECK(line === exp, what)
    end
  endtask

