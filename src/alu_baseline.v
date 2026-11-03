// 8-bit Baseline Arithmetic Logic Unit (ALU)
// Operations:
// 3'b000: ADD (out = a + b)
// 3'b001: SUB (out = a - b)
// 3'b010: AND (out = a & b)
// 3'b011: OR  (out = a | b)
// 3'b100: XOR (out = a ^ b)

module alu_baseline (
    input  wire [7:0] a,
    input  wire [7:0] b,
    input  wire [2:0] opcode,
    output reg  [7:0] alu_out,
    output reg        carry_out,
    output wire       zero
);

    localparam OP_ADD = 3'b000;
    localparam OP_SUB = 3'b001;
    localparam OP_AND = 3'b010;
    localparam OP_OR  = 3'b011;
    localparam OP_XOR = 3'b100;

    reg [8:0] arith_result;

    always @(*) begin
        arith_result = 9'b0;
        alu_out      = 8'b0;
        carry_out    = 1'b0;

        case (opcode)
            OP_ADD: begin
                arith_result = a + b;
                alu_out      = arith_result[7:0];
                carry_out    = arith_result[8];
            end
            OP_SUB: begin
                arith_result = a - b;
                alu_out      = arith_result[7:0];
                carry_out    = arith_result[8];
            end
            OP_AND: begin
                alu_out      = a & b;
                carry_out    = 1'b0;
            end
            OP_OR: begin
                alu_out      = a | b;
                carry_out    = 1'b0;
            end
            OP_XOR: begin
                alu_out      = a ^ b;
                carry_out    = 1'b0;
            end
            default: begin
                alu_out      = 8'b0;
                carry_out    = 1'b0;
            end
        endcase
    end

    assign zero = (alu_out == 8'b0000_0000);

endmodule
