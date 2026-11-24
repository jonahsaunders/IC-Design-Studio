// SPDX-License-Identifier: GPL-3.0-or-later
module beacon_run(input wire clk, rst_n, ena, input wire [7:0] ui_in, uio_in,
    output wire [7:0] uo_out, uio_out, uio_oe);
  wire [9:0] x, y;
  wire active, hsync, vsync, frame_tick, won;
  wire [6:0] rover_x, rover_y, obstacle_x;
  wire [2:0] collected;
  beacon_timing timing(clk, rst_n, x, y, active, hsync, vsync, frame_tick);
  beacon_game game(clk, rst_n, frame_tick && ena, ui_in[4:0],
      rover_x, rover_y, obstacle_x, collected, won);
  wire [6:0] tile_x = x[9:3];
  wire [6:0] tile_y = y[9:3];
  wire border = x < 8 || x >= 632 || y < 8 || y >= 472;
  wire upper_left = x < 24 && y < 24;
  wire upper_right = x >= 616 && y < 24;
  wire lower_left = x < 24 && y >= 456;
  wire lower_right = x >= 616 && y >= 456;
  wire rover = tile_x == rover_x && tile_y == rover_y;
  wire home = tile_x == 8 && tile_y == 8;
  wire beacon = (tile_x == 12 && tile_y == 8 && !collected[0]) ||
                (tile_x == 12 && tile_y == 12 && !collected[1]) ||
                (tile_x == 8 && tile_y == 12 && !collected[2]);
  wire obstacle = tile_x == obstacle_x && tile_y == 20;
  wire score_slot = tile_y == 4 && tile_x >= 4 && tile_x <= 6;
  wire score_lit = (tile_x == 4 && collected[0]) || (tile_x == 5 && collected[1]) ||
                   (tile_x == 6 && collected[2]);
  reg [5:0] rgb;
  always @* begin
    rgb = 0;
    if (active && ena) begin
      // Lesson 2: draw rover, uncollected beacons, and home above the border.
      if (upper_left) rgb = 6'b11_00_00;
      // Lesson 1: add the other three corners above the border.
      else if (border) rgb = 6'b01_01_01;
      else rgb = 6'b00_00_01;
      // Lesson 5: show the obstacle and a distinct win state.
    end
  end
  assign uo_out = {hsync, rgb[0], rgb[2], rgb[4], vsync, rgb[1], rgb[3], rgb[5]};
  assign uio_out = 0;
  assign uio_oe = 0;
endmodule
