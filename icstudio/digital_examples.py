"""Small designs with executable behavioral acceptance tests."""
from .digital import counter_project
from .model import validate


def uart_project():
    p=counter_project();p['name']='Digital UART transmitter';p['cells'][0]['name']='uart_tx'
    p['digital'].update(top='uart_tx',testbench='uart_tb',tests=[
        {'name':'UART frames / Icarus','testbench':'uart_tb','simulator':'icarus'},
        {'name':'UART frames / Verilator','testbench':'uart_tb','simulator':'verilator','coverage':True}])
    p['digital']['files']=[{'path':'uart_tx.sv','role':'rtl','text':'''`timescale 1ns/1ps
module uart_tx #(parameter integer DIVISOR = 4)(
  input wire clk, input wire reset, input wire send, input wire [7:0] data,
  output reg tx, output reg busy
);
  reg [9:0] frame;
  reg [3:0] bit_index;
  integer ticks;
  always @(posedge clk) begin
    if (reset) begin
      tx <= 1; busy <= 0; frame <= 10'h3ff; bit_index <= 0; ticks <= 0;
    end else if (!busy) begin
      if (send) begin
        frame <= {1'b1, data, 1'b0}; tx <= 0; busy <= 1;
        bit_index <= 0; ticks <= DIVISOR - 1;
      end
    end else if (ticks != 0) ticks <= ticks - 1;
    else if (bit_index == 9) begin busy <= 0; tx <= 1; end
    else begin
      bit_index <= bit_index + 1'b1; tx <= frame[bit_index + 1'b1];
      ticks <= DIVISOR - 1;
    end
  end
endmodule
'''},{'path':'uart_tb.sv','role':'testbench','text':'''`timescale 1ns/1ps
module uart_tb;
  reg clk = 0;
  reg reset = 1;
  reg send = 0;
  reg [7:0] data = 0;
  wire tx, busy;
  uart_tx dut(.clk(clk),.reset(reset),.send(send),.data(data),.tx(tx),.busy(busy));
  always #5 clk = ~clk;
  task check_frame(input [7:0] value);
    reg [9:0] expected;
    integer bit_number;
    begin
      expected = {1'b1, value, 1'b0};
      @(negedge clk); data = value; send = 1;
      @(negedge clk); send = 0;
      if (!busy) $fatal(1,"UART did not accept a byte");
      for (bit_number=0; bit_number<10; bit_number=bit_number+1) begin
        if (tx !== expected[bit_number]) $fatal(1,"UART frame bit mismatch");
        repeat (4) @(negedge clk);
      end
      if (busy || tx !== 1'b1) $fatal(1,"UART did not return to idle");
    end
  endtask
  initial begin
    $dumpfile("wave.vcd"); $dumpvars(0,uart_tb);
    repeat (2) @(negedge clk);
    if (tx !== 1'b1 || busy !== 1'b0) $fatal(1,"UART reset failed");
    reset = 0;
    check_frame(8'h00); check_frame(8'ha5); check_frame(8'hff);
    $display("UART checks passed: reset, start/data/stop bits and idle");
    $finish;
  end
  initial begin #10000; $fatal(1,"UART test timed out"); end
endmodule
'''},{'path':'constraints.sdc','role':'constraint','text':'''create_clock -name core_clk -period 10 [get_ports clk]
set_input_delay 1 -clock core_clk [get_ports {reset send data*}]
set_output_delay 1 -clock core_clk [get_ports {tx busy}]
'''}]
    return validate(p)
