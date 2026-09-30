// Eight conversions, averaged in non-overlapping groups of four.
// Start pulses come from the experiment; no hidden Python conversion logic.
module sensor_controller(
    input wire clk, reset, start, cmp,
    output wire [3:0] dac, code,
    output wire track, busy, done, compare,
    output reg [3:0] average,
    output reg average_valid, alarm,
    output reg [3:0] sample_count
);
  sar_controller adc(clk, reset, start, cmp, dac, code, track, busy, done, compare);
  reg [5:0] sum;
  reg [1:0] count;
  wire [5:0] total = sum + {2'b0, code};
  wire [3:0] rounded_average = (total + 6'd2) >> 2;
  always @(posedge clk) begin
    if (reset) begin
      sum <= 0; count <= 0; average <= 0;
      average_valid <= 0; alarm <= 0; sample_count <= 0;
    end else begin
      average_valid <= 0;
      if (done) begin
        sample_count <= sample_count + 1;
        if (count == 3) begin
          average <= rounded_average;
          alarm <= (rounded_average >= 10);
          average_valid <= 1; sum <= 0; count <= 0;
        end else begin
          sum <= total; count <= count + 1;
        end
      end
    end
  end
endmodule
