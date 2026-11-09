// 8-bit Low-Power Optimized Arithmetic Logic Unit (ALU)
// Low-Power & Area Optimizations:
// 1. Operand Isolation (Input Gating): Arithmetic and logical operands are forced to 0 
//    when their respective operations are inactive, preventing unnecessary dynamic 
//    switching in idle sub-circuits.
// 2. Resource Sharing: A single shared 9-bit adder/subtractor is used for both 
//    ADD and SUB operations using two's complement inversion and carry-in (`cin`).
// 3. Glitch mitigation and concise combinational logic structure.

module alu_optimized (
    input  wire [7:0] a,
    input  wire [7:0] b,
    input  wire [2:0] opcode,
    output reg  [7:0] alu_out,
    output reg        carry_out,
    output wire       zero
);

    // Opcode definitions
    localparam OP_ADD = 3'b000;
    localparam OP_SUB = 3'b001;
    localparam OP_AND = 3'b010;
    localparam OP_OR  = 3'b011;
    localparam OP_XOR = 3'b100;

    // 1. Operand Isolation: 
    // Identify if the current operation requires the arithmetic datapath.
    // If not, gate the inputs to 8'h00 to prevent internal toggling.
    wire is_arith = (opcode == OP_ADD) || (opcode == OP_SUB);
    wire [7:0] arith_a = is_arith ? a : 8'b0;
    wire [7:0] arith_b = is_arith ? b : 8'b0;

    // 2. Shared Adder/Subtractor Logic:
    // SUB is performed as: arith_a + (~arith_b) + 1
    wire is_sub    = (opcode == OP_SUB);
    wire [7:0] b_operand = is_sub ? ~arith_b : arith_b;
    wire       cin       = is_sub;

    // 9-bit unified arithmetic result capturing carry/borrow
    wire [8:0] arith_res = arith_a + b_operand + {8'b0, cin};

    // 3. Logic Datapath with Operand Isolation
    wire is_logic = (opcode == OP_AND) || (opcode == OP_OR) || (opcode == OP_XOR);
    wire [7:0] logic_a = is_logic ? a : 8'b0;
    wire [7:0] logic_b = is_logic ? b : 8'b0;

    wire [7:0] and_res = logic_a & logic_b;
    wire [7:0] or_res  = logic_a | logic_b;
    wire [7:0] xor_res = logic_a ^ logic_b;

    // Multiplexing outputs based on opcode
    always @(*) begin
        // Default assignments
        alu_out   = 8'b0;
        carry_out = 1'b0;

        case (opcode)
            OP_ADD: begin
                alu_out   = arith_res[7:0];
                carry_out = arith_res[8];
            end
            OP_SUB: begin
                alu_out   = arith_res[7:0];
                // For SUB, carry_out represents the borrow flag:
                // 1 if A < B (arith_res[8] == 0), 0 if A >= B (arith_res[8] == 1)
                carry_out = ~arith_res[8];
            end
            OP_AND: begin
                alu_out   = and_res;
                carry_out = 1'b0;
            end
            OP_OR: begin
                alu_out   = or_res;
                carry_out = 1'b0;
            end
            OP_XOR: begin
                alu_out   = xor_res;
                carry_out = 1'b0;
            end
            default: begin
                alu_out   = 8'b0;
                carry_out = 1'b0;
            end
        endcase
    end

    // Zero flag generation
    assign zero = (alu_out == 8'b0000_0000);

endmodule
