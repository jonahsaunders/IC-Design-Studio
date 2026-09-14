"""Hierarchical APB FIFO peripheral and an executable protocol/behavior regression."""
from .digital import counter_project
from .digital_constraints import apply
from .model import validate


FIFO = '''`timescale 1ns/1ps
module byte_fifo(input wire clk, reset, push, pop, input wire [7:0] din,
                 output wire [7:0] dout, output wire full, empty, output reg [2:0] count);
  reg [7:0] mem[0:3];
  reg [1:0] wr, rd;
  assign full = count == 4;
  assign empty = count == 0;
  assign dout = empty ? 8'h00 : mem[rd];
  always @(posedge clk) begin
    if (reset) begin wr <= 0; rd <= 0; count <= 0; end
    else begin
      if (push && !full) begin mem[wr] <= din; wr <= wr + 1'b1; end
      if (pop && !empty) rd <= rd + 1'b1;
      case ({push && !full, pop && !empty})
        2'b10: count <= count + 1'b1;
        2'b01: count <= count - 1'b1;
        default: count <= count;
      endcase
    end
  end
endmodule
'''

PERIPHERAL = '''`timescale 1ns/1ps
module apb_fifo(input wire clk, reset, psel, penable, pwrite,
  input wire [3:0] paddr, input wire [7:0] pwdata,
  output reg [7:0] prdata, output wire pready, pslverr, irq);
  wire full, empty; wire [2:0] count; wire [7:0] dout;
  reg irq_enable;
  wire transfer = psel && penable;
  wire data_access = paddr == 0;
  wire invalid = paddr != 0 && paddr != 4 && paddr != 8;
  assign pready = 1'b1;
  assign pslverr = transfer && (invalid || (pwrite && paddr == 4) ||
                   (data_access && (pwrite ? full : empty)));
  assign irq = irq_enable && !empty;
  byte_fifo fifo(.clk(clk),.reset(reset),.push(transfer && data_access && pwrite),
    .pop(transfer && data_access && !pwrite),.din(pwdata),.dout(dout),
    .full(full),.empty(empty),.count(count));
  always @* begin
    case (paddr)
      0: prdata = dout;
      4: prdata = {3'b000,full,empty,count};
      8: prdata = {7'b0,irq_enable};
      default: prdata = 0;
    endcase
  end
  always @(posedge clk)
    if (reset) irq_enable <= 0;
    else if (transfer && pwrite && paddr == 8) irq_enable <= pwdata[0];
endmodule
'''

BENCH = '''`timescale 1ns/1ps
module apb_fifo_tb;
  reg clk=0, reset=1, psel=0, penable=0, pwrite=0;
  reg [3:0] paddr=0; reg [7:0] pwdata=0;
  wire [7:0] prdata; wire pready, pslverr, irq;
  integer i;
  apb_fifo dut(.*);
  always #5 clk=~clk;
  task access(input bit wr, input [3:0] addr, input [7:0] value,
              input [7:0] expected, input bit error);
    begin
      @(negedge clk); psel=1; penable=0; pwrite=wr; paddr=addr; pwdata=value;
      @(negedge clk); penable=1;
      #1;
      if (pready !== 1 || pslverr !== error) $fatal(1,"APB response mismatch");
      if (!wr && prdata !== expected) $fatal(1,"APB read mismatch");
      @(negedge clk); psel=0; penable=0;
    end
  endtask
  initial begin
    $dumpfile("wave.vcd"); $dumpvars(0,apb_fifo_tb);
    repeat(2) @(negedge clk); reset=0;
    access(0,4,0,8'h08,0); // empty
    access(0,0,0,0,1); // empty read error, no pointer advance
    access(1,8,1,0,0); // interrupt enable
    // Hold setup for multiple cycles: no write is allowed before access.
    @(negedge clk); psel=1; penable=0; pwrite=1; paddr=0; pwdata=8'hee;
    repeat(3) @(negedge clk);
    if (irq !== 0) $fatal(1,"APB setup performed a write");
    psel=0;
    for(i=0;i<4;i=i+1) access(1,0,8'h40+i[7:0],0,0);
    if (irq !== 1) $fatal(1,"FIFO interrupt mismatch");
    access(0,4,0,8'h14,0); // full, count=4
    access(1,0,8'hff,0,1); // full write rejected
    for(i=0;i<4;i=i+1) access(0,0,0,8'h40+i[7:0],0);
    if (irq !== 0) $fatal(1,"FIFO empty interrupt mismatch");
    // Wrap both pointers, preserve ordering, then reset with buffered data.
    repeat(3) begin access(1,0,8'ha5,0,0); access(0,0,0,8'ha5,0); end
    access(1,12,0,0,1); access(1,4,0,0,1);
    access(1,0,8'h55,0,0);
    @(negedge clk); reset=1; @(negedge clk); reset=0;
    access(0,4,0,8'h08,0); access(0,8,0,0,0);
    $display("APB FIFO checks passed: setup/access, ordering, full/empty, wrap, errors, interrupt and reset");
    $finish;
  end
  initial begin #20000; $fatal(1,"APB FIFO timeout"); end
endmodule
'''


def apb_project():
    p=counter_project();p['name']='APB FIFO peripheral';p['cells'][0]['name']='apb_fifo'
    p['digital'].update(top='apb_fifo',testbench='apb_fifo_tb',timeout=180,tests=[
        {'name':'APB FIFO / Icarus','testbench':'apb_fifo_tb','simulator':'icarus'},
        {'name':'APB FIFO / Verilator','testbench':'apb_fifo_tb','simulator':'verilator','coverage':True}])
    p['digital']['files']=[{'path':name,'role':role,'text':text} for name,role,text in (
        ('byte_fifo.sv','rtl',FIFO),('apb_fifo.sv','rtl',PERIPHERAL),('apb_fifo_tb.sv','testbench',BENCH))]
    p['digital']=apply(p['digital'],{'version':1,'clocks':[{'name':'core_clk','port':'clk','period_ns':20,'uncertainty_ns':.1}],
        'inputs':[{'ports':'reset psel penable pwrite paddr* pwdata*','clock':'core_clk','min_ns':0,'max_ns':1}],
        'outputs':[{'ports':'prdata* pready pslverr irq','clock':'core_clk','min_ns':0,'max_ns':1}],'load_pf':.01})
    return validate(p)
