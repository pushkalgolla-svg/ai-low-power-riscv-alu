// 32-bit Standard RISC-V (RV32I) ALU - Structurally Optimized & Low-Power
// Implements the 10 standard integer computational instructions with:
// 1. Operand Isolation (Input Gating) to suppress redundant toggling in heavy arithmetic/shift blocks.
// 2. Resource Sharing: Unified single 32-bit adder for ADD, SUB, SLT, and SLTU.

module riscv_alu_optimized (
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

    // Instruction category decodes for operand isolation and routing
    wire is_arith = (alu_ctrl == ALU_ADD)  || 
                    (alu_ctrl == ALU_SUB)  || 
                    (alu_ctrl == ALU_SLT)  || 
                    (alu_ctrl == ALU_SLTU);

    wire is_shift = (alu_ctrl == ALU_SLL)  || 
                    (alu_ctrl == ALU_SRL)  || 
                    (alu_ctrl == ALU_SRA);

    wire is_logic = (alu_ctrl == ALU_XOR)  || 
                    (alu_ctrl == ALU_OR)   || 
                    (alu_ctrl == ALU_AND);

    // =========================================================================
    // 1. OPERAND ISOLATION (INPUT GATING)
    // Prevents dynamic power dissipation by freezing inputs to massive datapath
    // blocks (adder/subtractor and barrel shifter) when those blocks are idle.
    // =========================================================================
    wire [31:0] arith_a    = is_arith ? a : 32'b0;
    wire [31:0] arith_b    = is_arith ? b : 32'b0;
    
    wire [31:0] shift_a    = is_shift ? a : 32'b0;
    wire [4:0]  shift_amt  = is_shift ? b[4:0] : 5'b0;

    // =========================================================================
    // 2. RESOURCE-SHARED UNIFIED ADDER/SUBTRACTOR & COMPARATOR DATAPATH
    // Uses a single 32-bit adder for ADD, SUB, SLT, and SLTU computations.
    // =========================================================================
    // SUB, SLT, and SLTU all utilize the subtraction path (b_comp = ~b, cin = 1)
    wire        sub_op     = (alu_ctrl != ALU_ADD);
    wire [31:0] b_comp     = sub_op ? ~arith_b : arith_b;
    
    // 33-bit addition for carry-out (unsigned borrow) detection
    wire [32:0] add_sub_res = {1'b0, arith_a} + {1'b0, b_comp} + {32'b0, sub_op};

    // Correct signed comparison handling overflow conditions for SLT
    // If sign bits differ, a[31] < b[31] directly dictates the relation.
    // If sign bits match, the subtraction result sign bit (add_sub_res[31]) is valid.
    wire        slt_res    = (arith_a[31] != arith_b[31]) ? arith_a[31] : add_sub_res[31];
    
    // Unsigned comparison using the carry-out from the adder/subtractor
    wire        sltu_res   = ~add_sub_res[32];

    // =========================================================================
    // 3. BARREL SHIFTER DATAPATH
    // =========================================================================
    reg [31:0] shift_res;
    always @(*) begin
        case (alu_ctrl)
            ALU_SLL:  shift_res = shift_a << shift_amt;
            ALU_SRL:  shift_res = shift_a >> shift_amt;
            ALU_SRA:  shift_res = $signed(shift_a) >>> shift_amt;
            default:  shift_res = 32'b0;
        endcase
    end

    // =========================================================================
    // 4. LOGICAL DATAPATH
    // =========================================================================
    wire [31:0] logic_res = (alu_ctrl == ALU_XOR) ? (a ^ b) :
                            (alu_ctrl == ALU_OR)  ? (a | b) :
                            (alu_ctrl == ALU_AND) ? (a & b) : 32'b0;

    // =========================================================================
    // 5. OUTPUT MULTIPLEXING
    // =========================================================================
    always @(*) begin
        case (alu_ctrl)
            ALU_ADD, 
            ALU_SUB:  alu_out = add_sub_res[31:0];
            ALU_SLL, 
            ALU_SRL, 
            ALU_SRA:  alu_out = shift_res;
            ALU_SLT:  alu_out = {31'b0, slt_res};
            ALU_SLTU: alu_out = {31'b0, sltu_res};
            ALU_XOR, 
            ALU_OR, 
            ALU_AND:  alu_out = logic_res;
            default:  alu_out = 32'h0000_0000;
        endcase
    end

    assign zero = (alu_out == 32'h0000_0000);

endmodule