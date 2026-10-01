// Four-bit, MSB-first SAR controller. The analog comparator supplies cmp.
// DAC outputs are held for a full clock before each comparator decision.
module sar_controller(
    input wire clk, input wire reset, input wire start, input wire cmp,
    output reg [3:0] dac, output reg [3:0] code,
    output reg track, output reg busy, output reg done,
    output wire compare
);
  localparam IDLE=0, ACQUIRE=1, CONVERT=2;
  reg [1:0] state;
  reg [1:0] bit_index;
  reg [3:0] accepted;
  assign compare = (state == CONVERT);
  always @(posedge clk) begin
    if (reset) begin
      state <= IDLE; bit_index <= 3;
      dac <= 0; code <= 0; track <= 1; busy <= 0; done <= 0;
    end else begin
      done <= 0;
      case (state)
        IDLE: if (start) begin
          track <= 1; busy <= 1; dac <= 0; state <= ACQUIRE;
        end
        ACQUIRE: begin
          track <= 0; dac <= 4'b1000; bit_index <= 3; state <= CONVERT;
        end
        CONVERT: begin
          accepted = dac;
          if (!cmp) accepted[bit_index] = 0;
          if (bit_index == 0) begin
            dac <= accepted; code <= accepted;
            busy <= 0; done <= 1; state <= IDLE;
          end else begin
            dac <= accepted | (4'b0001 << (bit_index-1));
            bit_index <= bit_index-1;
          end
        end
        default: begin state <= IDLE; busy <= 0; track <= 1; dac <= 0; end
      endcase
    end
  end
endmodule
