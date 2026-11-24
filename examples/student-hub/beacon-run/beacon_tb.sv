// SPDX-License-Identifier: GPL-3.0-or-later
`timescale 1ns/1ps
module beacon_tb;
  reg clk=0, rst_n=0, tick=0;
  reg [4:0] buttons=0;
  wire [6:0] rx, ry, ox;
  wire [2:0] collected;
  wire won;
  wire [7:0] pixel, spare, oe;
  beacon_run dut(clk,rst_n,1'b1,8'd0,8'd0,pixel,spare,oe);
  beacon_game game(clk,rst_n,tick,buttons,rx,ry,ox,collected,won);
  always #19.861 clk=~clk;

  function [5:0] rgb(input [7:0] pins);
    rgb={pins[0],pins[4],pins[1],pins[5],pins[2],pins[6]};
  endfunction

  task frame(input [4:0] keys);
    buttons=keys; tick=1; @(negedge clk); tick=0;
  endtask

  task reset;
    rst_n=0; tick=0; buttons=0;
    @(negedge clk); rst_n=1;
  endtask

  integer cycle, x, y;
  reg timing_ok=1, board_ok=1, move_ok=1, score_ok=1, finish_ok=1;
  initial begin
    $dumpfile("wave.vcd");
    $dumpvars(1, beacon_tb);
    $dumpvars(1, dut.timing);
    $dumpvars(1, game);
    reset;
    // Sample the complete unmodified pixel raster through the TinyVGA pins.
    for (cycle=0; cycle<800*525; cycle=cycle+1) begin
      x=cycle%800; y=cycle/800;
      if (dut.timing.x !== x[9:0] || dut.timing.y !== y[9:0] ||
          dut.timing.frame_tick !== (cycle==800*525-1) ||
          pixel[7] !== !(x>=656 && x<752) || pixel[3] !== !(y>=490 && y<492)) timing_ok=0;
      if ((x>=640 || y>=480) && rgb(pixel)!==0) timing_ok=0;
      if (x==12 && y==12 && rgb(pixel)!==6'b11_00_00) timing_ok=0;
      if (x==627 && y==12 && rgb(pixel)!==6'b00_11_00) timing_ok=0;
      if (x==12 && y==467 && rgb(pixel)!==6'b00_00_11) timing_ok=0;
      if (x==627 && y==467 && rgb(pixel)!==6'b11_11_00) timing_ok=0;
      if (x==320 && y==2 && rgb(pixel)!==6'b01_01_01) timing_ok=0;
      if (x==66 && y==66 && rgb(pixel)!==6'b00_11_11) board_ok=0;
      if ((x==100 && (y==66 || y==100) || x==66 && y==100) && rgb(pixel)!==6'b11_10_00) board_ok=0;
      if (x==250 && y==162 && rgb(pixel)!==6'b11_00_00 && rgb(pixel)!==6'b00_00_01) board_ok=0;
      @(negedge clk);
    end
    if (dut.timing.x!==0 || dut.timing.y!==0) timing_ok=0;
    if (timing_ok) $display("STUDENT_CHECKS PASS beacon_run timing");
    else $display("CHECK timing: inspect the sync interval, blanking and four corner colors");
    if (timing_ok && board_ok) $display("STUDENT_CHECKS PASS beacon_run board");

    buttons=5'b00010; repeat (3) @(negedge clk);
    if (rx!==8 || ry!==8) move_ok=0;
    frame(5'b00010); if (rx!==9 || ry!==8) move_ok=0;
    frame(5'b00011); if (rx!==9 || ry!==8) move_ok=0;
    repeat (12) frame(5'b00101); if (rx!==1 || ry!==1) move_ok=0;
    repeat (80) frame(5'b01010); if (rx!==78 || ry!==58) move_ok=0;
    if (timing_ok && board_ok && move_ok) $display("STUDENT_CHECKS PASS beacon_run movement");
    else $display("CHECK movement: use one step per frame, cancel opposites, and stop at the border");

    reset;
    repeat (4) frame(5'b00010); if (collected!==3'b001) score_ok=0;
    repeat (4) frame(0); if (collected!==3'b001) score_ok=0;
    repeat (4) frame(5'b01000); if (collected!==3'b011) score_ok=0;
    repeat (4) frame(5'b00001); if (collected!==3'b111) score_ok=0;
    force dut.timing.x=32; force dut.timing.y=32;
    force dut.game.collected=3'b001; #1;
    if (rgb(pixel)!==6'b11_11_00) score_ok=0;
    force dut.timing.x=40; #1;
    if (rgb(pixel)!==6'b01_01_01) score_ok=0;
    release dut.timing.x; release dut.timing.y; release dut.game.collected;
    if (timing_ok && board_ok && move_ok && score_ok) $display("STUDENT_CHECKS PASS beacon_run collect");
    else $display("CHECK collect: hold position on the first beacon and preserve the three-bit collection mask");

    if (won!==0) finish_ok=0;
    repeat (4) frame(5'b00100); if (won!==1) finish_ok=0;
    frame(5'b00010); if (rx!==8 || ry!==8 || won!==1) finish_ok=0;
    frame(5'b10000); if (rx!==8 || ry!==8 || won!==0 || collected!==0 || ox!==30) finish_ok=0;
    frame(0); if (ox!==31) finish_ok=0;
    // An already positioned rover will meet the next obstacle tile at the frame tick.
    game.rover_x=32; game.rover_y=20; game.collected=3'b011;
    frame(0); if (rx!==8 || ry!==8 || collected!==0 || won!==0) finish_ok=0;
    force dut.timing.x=250; force dut.timing.y=162;
    force dut.game.obstacle_x=31; #1;
    if (rgb(pixel)!==6'b11_00_00) finish_ok=0;
    force dut.game.won=1; #1;
    if (rgb(pixel)!==6'b00_11_00) finish_ok=0;
    if (timing_ok && board_ok && move_ok && score_ok && finish_ok)
      $display("STUDENT_CHECKS PASS beacon_run finish");
    else $display("CHECK finish: return home after collecting, freeze on win, and reset on collision or restart");
    $finish;
  end
endmodule
