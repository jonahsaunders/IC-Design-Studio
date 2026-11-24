"""Mode-0 register peripheral with a separate fault-detecting lesson bench."""

PORTS = 'input wire clk,reset,cs_n,sclk,mosi, output wire miso'
BODY = """
  reg [7:0] memory [0:3];
  reg [2:0] cs_sync, clk_sync;
  reg [1:0] data_sync;
  reg [4:0] bits;
  reg [7:0] rx, tx;
  reg [1:0] address;
  reg selected_read, valid_address, output_bit, output_valid;
  integer i;

  wire [7:0] received = {rx[6:0], data_sync[1]};
  wire frame_end = cs_sync[1] && !cs_sync[2];
  wire rise = clk_sync[1] && !clk_sync[2];
  wire fall = !clk_sync[1] && clk_sync[2];
  assign miso = cs_n || !output_valid ? 1'bz : output_bit;

  always @(posedge clk) begin
    if (reset) begin
      cs_sync <= 3'b111; clk_sync <= 0; data_sync <= 0;
      bits <= 0; rx <= 0; tx <= 0; address <= 0;
      selected_read <= 0; valid_address <= 0; output_bit <= 0; output_valid <= 0;
      for (i=0; i<4; i=i+1) memory[i] <= 0;
    end else begin
      cs_sync <= {cs_sync[1:0], cs_n};
      clk_sync <= {clk_sync[1:0], sclk};
      data_sync <= {data_sync[0], mosi};
      if (frame_end) begin
        // Commit the write only when an entire frame was received.
        if (!selected_read && valid_address && bits >= 12)
          memory[address] <= rx;
        bits <= 0; rx <= 0; selected_read <= 0; valid_address <= 0; output_valid <= 0;
      end else if (!cs_sync[1]) begin
        if (rise) begin
          if (bits < 17) bits <= bits + 1;
          rx <= received;
          if (bits == 7) begin
            selected_read <= received[7];
            valid_address <= received[6:2] == 0;
            address <= received[1:0];
            tx <= memory[received[1:0]];
          end
        end
        if (fall && selected_read && valid_address && bits >= 8 && bits < 16) begin
          output_bit <= tx[15-bits];
          output_valid <= 1;
        end
      end
    end
  end
"""

DECLARATIONS = """
  reg clk=0, reset=1, cs_n=1, sclk=0, mosi=0;
  wire miso;
  reg [7:0] rx;
  always #5 clk=~clk;

  task begin_frame;
    begin cs_n=0; #80; end
  endtask

  task finish_frame;
    begin
      cs_n=1; #100;
      if (miso !== 1'bz) $fatal(1,"MISO did not release when deselected");
    end
  endtask

  task shift_byte(input [7:0] payload, input integer count, output [7:0] received);
    integer b;
    begin
      received=0;
      for (b=7; b>=8-count; b=b-1) begin
        mosi=payload[b]; #80; sclk=1; #2; received[b]=miso;
        #76;
        if (received[b] !== miso) $fatal(1,"MISO changed within a high clock phase");
        #2; sclk=0;
      end
    end
  endtask

  task read_back(input [1:0] address, input [7:0] expected);
    reg [7:0] unused, value;
    begin
      begin_frame;
      shift_byte({6'b100000,address},8,unused);
      shift_byte(0,8,value);
      finish_frame;
      if (value !== expected)
        $fatal(1,"Read register %d expected %h got %h",address,expected,value);
    end
  endtask
"""

CHECKS = """
  #42; reset=0; #70;
  read_back(0,0);
  begin_frame;
  shift_byte(8'h01,8,rx); shift_byte(8'hA5,8,rx);
  finish_frame;
  read_back(1,8'hA5);
  begin_frame;
  shift_byte(8'h01,8,rx); shift_byte(8'hF0,4,rx);
  finish_frame;
  read_back(1,8'hA5);
  begin_frame;
  shift_byte(8'h01,8,rx); shift_byte(8'h2C,8,rx); shift_byte(8'h80,1,rx);
  finish_frame;
  read_back(1,8'hA5);
  begin_frame;
  shift_byte(8'h05,8,rx); shift_byte(8'hFF,8,rx);
  finish_frame;
  read_back(1,8'hA5);
  begin_frame;
  shift_byte(8'h03,8,rx); shift_byte(8'h96,8,rx);
  finish_frame;
  read_back(3,8'h96);
  read_back(0,0); read_back(2,0);
  reset=1; #60; reset=0; #80;
  read_back(1,0); read_back(3,0);
"""

SPI_REGISTER = PORTS, BODY, DECLARATIONS, 'clk,reset,cs_n,sclk,mosi,miso', CHECKS
