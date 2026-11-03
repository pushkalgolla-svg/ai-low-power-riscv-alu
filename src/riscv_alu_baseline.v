// 32-bit Standard RISC-V (RV32I) ALU Baseline
// Implements the 10 standard integer computational instructions:
// 4'b0000: ADD  (out = a + b)
// 4'b0001: SUB  (out = a - b)
// 4'b0010: SLL  (out = a << b[4:0])             - Shift Left Logical
// 4'b0011: SLT  (out = ($signed(a) < $signed(b)) ? 1 : 0) - Set Less Than (signed)
// 4'b0100: SLTU (out = (a < b) ? 1 : 0)         - Set Less Than (unsigned)
// 4'b0101: XOR  (out = a ^ b)
// 4'b0110: SRL  (out = a >> b[4:0])             - Shift Right Logical
// 4'b0111: SRA  (out = $signed(a) >>> b[4:0])   - Shift Right Arithmetic
// 4'b1000: OR   (out = a | b)
// 4'b1001: AND  (out = a & b)

module riscv_alu_baseline (
    input  wire [31:0] a,
    input  wire [31:0] b,
    input  wire [3:0]  alu_ctrl,
    output reg  [31:0] alu_out,
    output wire        zero
);

    localparam ALU_ADD  = 4'b0000;
    localparam ALU_SUB  = 4'b0001;
    localparam ALU_SLL  = 4'b0010;
    localparam ALU_SLT  = 4'b0011;
    localparam ALU_SLTU = 4'b0100;
    localparam ALU_XOR  = 4'b0101;
    localparam ALU_SRL  = 4'b0110;
    localparam ALU_SRA  = 4'b0111;
    localparam ALU_OR   = 4'b1000;
    localparam ALU_AND  = 4'b1001;

    wire [4:0] shamt = b[4:0];

    always @(*) begin
        case (alu_ctrl)
            ALU_ADD:  alu_out = a + b;
            ALU_SUB:  alu_out = a - b;
            ALU_SLL:  alu_out = a << shamt;
            ALU_SLT:  alu_out = ($signed(a) < $signed(b)) ? 32'd1 : 32'd0;
            ALU_SLTU: alu_out = (a < b) ? 32'd1 : 32'd0;
            ALU_XOR:  alu_out = a ^ b;
            ALU_SRL:  alu_out = a >> shamt;
            ALU_SRA:  alu_out = $signed(a) >>> shamt;
            ALU_OR:   alu_out = a | b;
            ALU_AND:  alu_out = a & b;
            default:  alu_out = 32'h0000_0000;
        endcase
    end

    assign zero = (alu_out == 32'h0000_0000);

endmodule
