// SPDX-License-Identifier: GPL-3.0-or-later
module beacon_game(input wire clk, rst_n, frame_tick, input wire [4:0] buttons,
    output reg [6:0] rover_x, rover_y, obstacle_x,
    output reg [2:0] collected, output reg won);
  reg [6:0] next_x, next_y;
  wire [6:0] next_obstacle = obstacle_x == 46 ? 7'd30 : obstacle_x + 1'b1;
  wire hit_obstacle = next_y == 20 && next_x == next_obstacle;
  wire entered_home = next_x == 8 && next_y == 8;
  wire [2:0] touched = {next_x == 8 && next_y == 12,
                        next_x == 12 && next_y == 12,
                        next_x == 12 && next_y == 8};

  always @* begin
    next_x = rover_x;
    next_y = rover_y;
    // Lesson 3: fill in opposite-direction cancellation and border guards.
    //  ui_in[0:3] are left, right, up, down respectively.
  end

  always @(posedge clk) begin
    if (!rst_n) begin
      rover_x <= 8; rover_y <= 8; obstacle_x <= 30;
      collected <= 0; won <= 0;
    end else if (frame_tick) begin
      rover_x <= next_x; rover_y <= next_y;
      // Lesson 4: latch touched beacons so a held overlap only counts once.
      collected <= collected;
      // Lesson 5: move the obstacle and add collision, win and restart priority.
    end
  end
endmodule
