// SPDX-License-Identifier: GPL-3.0-or-later
module beacon_timing(input wire clk, rst_n, output reg [9:0] x, y,
    output wire active, hsync, vsync, frame_tick);
  assign active = x < 640 && y < 480;
  // Lesson 1: complete the 96-pixel active-low horizontal sync pulse.
  assign hsync = !(x >= 656 && x < 735);
  assign vsync = !(y >= 490 && y < 492);
  assign frame_tick = x == 799 && y == 524;
  always @(posedge clk) begin
    if (!rst_n) begin x <= 0; y <= 0; end
    else if (x == 799) begin
      x <= 0;
      if (y == 524) y <= 0;
      else y <= y + 1'b1;
    end else x <= x + 1'b1;
  end
endmodule
