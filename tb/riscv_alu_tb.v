`timescale 1ns/1ps

module riscv_alu_tb;

    reg  [31:0] a;
    reg  [31:0] b;
    reg  [3:0]  alu_ctrl;

    // Baseline DUT
    wire [31:0] base_out;
    wire        base_zero;

    riscv_alu_baseline dut_base (
        .a(a),
        .b(b),
        .alu_ctrl(alu_ctrl),
        .alu_out(base_out),
        .zero(base_zero)
    );

    // Optimized DUT (or candidate under evaluation)
    wire [31:0] opt_out;
    wire        opt_zero;

`ifdef TEST_CANDIDATE
    riscv_alu_candidate dut_opt (
`else
    riscv_alu_optimized dut_opt (
`endif
        .a(a),
        .b(b),
        .alu_ctrl(alu_ctrl),
        .alu_out(opt_out),
        .zero(opt_zero)
    );

    // =========================================================================
    // Activity Instrumentation Probes (Equivalent Logical Datapath Boundaries)
    // =========================================================================
    // 1. Functional Datapath Category Probes:
    // Arithmetic Datapath Inputs (Adder/Subtractor/Comparator)
    wire [31:0] base_probe_arith_a   = dut_base.a;
    wire [31:0] base_probe_arith_b   = dut_base.b;
    wire [31:0] opt_probe_arith_a    = dut_opt.arith_a;
    wire [31:0] opt_probe_arith_b    = dut_opt.arith_b;

    // Shift Datapath Inputs (Barrel Shifter)
    wire [31:0] base_probe_shift_a   = dut_base.a;
    wire [4:0]  base_probe_shift_amt = dut_base.shamt;
    wire [31:0] opt_probe_shift_a    = dut_opt.shift_a;
    wire [4:0]  opt_probe_shift_amt  = dut_opt.shift_amt;

    // Logic Datapath Inputs (AND/OR/XOR)
    wire [31:0] base_probe_logic_a   = dut_base.a;
    wire [31:0] base_probe_logic_b   = dut_base.b;
    wire [31:0] opt_probe_logic_a    = dut_opt.logic_a;
    wire [31:0] opt_probe_logic_b    = dut_opt.logic_b;

    // 2. Individual Baseline Operator Probes (Where baseline uses separate operations):
    wire [31:0] base_op_add_a        = dut_base.a;
    wire [31:0] base_op_add_b        = dut_base.b;
    wire [31:0] base_op_sub_a        = dut_base.a;
    wire [31:0] base_op_sub_b        = dut_base.b;
    wire [31:0] base_op_slt_a        = dut_base.a;
    wire [31:0] base_op_slt_b        = dut_base.b;
    wire [31:0] base_op_sll_a        = dut_base.a;
    wire [4:0]  base_op_sll_amt      = dut_base.shamt;
    wire [31:0] base_op_srl_a        = dut_base.a;
    wire [4:0]  base_op_srl_amt      = dut_base.shamt;
    wire [31:0] base_op_sra_a        = dut_base.a;
    wire [4:0]  base_op_sra_amt      = dut_base.shamt;

    // Independent Golden Reference Model
    reg [31:0] ref_out;
    reg        ref_zero;

    task golden_reference;
        input [31:0] in_a;
        input [31:0] in_b;
        input [3:0]  ctrl;
        output [31:0] out;
        output        z;
        reg [4:0] shamt;
        begin
            shamt = in_b[4:0];
            case (ctrl)
                4'b0000: out = in_a + in_b;                                         // ADD
                4'b0001: out = in_a - in_b;                                         // SUB
                4'b0010: out = in_a << shamt;                                       // SLL
                4'b0011: out = ($signed(in_a) < $signed(in_b)) ? 32'd1 : 32'd0;    // SLT
                4'b0100: out = (in_a < in_b) ? 32'd1 : 32'd0;                       // SLTU
                4'b0101: out = in_a ^ in_b;                                         // XOR
                4'b0110: out = in_a >> shamt;                                       // SRL
                4'b0111: out = $signed(in_a) >>> shamt;                             // SRA
                4'b1000: out = in_a | in_b;                                         // OR
                4'b1001: out = in_a & in_b;                                         // AND
                default: out = 32'h0000_0000;
            endcase
            z = (out == 32'h0000_0000);
        end
    endtask

    integer pass_count = 0;
    integer fail_count = 0;

    task apply_and_check;
        input [255:0] test_name;
        reg has_unknown;
        begin
            #10; // Propagation delay
            golden_reference(a, b, alu_ctrl, ref_out, ref_zero);

            // Reject unknown (X/Z) bits on all inputs and outputs
            has_unknown = (^a === 1'bx) || (^b === 1'bx) || (^alu_ctrl === 1'bx) ||
                          (^base_out === 1'bx) || (^opt_out === 1'bx) ||
                          (base_zero === 1'bx) || (opt_zero === 1'bx);

            if (!has_unknown &&
                base_out === ref_out && opt_out === ref_out &&
                base_zero === ref_zero && opt_zero === ref_zero) begin
                pass_count = pass_count + 1;
            end else begin
                fail_count = fail_count + 1;
                if (has_unknown) begin
                    $display("[FAIL - UNKNOWN VALUE X/Z] %s | Ctrl=%b, A=0x%08h, B=0x%08h", test_name, alu_ctrl, a, b);
                    $display("       BaseOut=0x%08h (Z=%b), OptOut=0x%08h (Z=%b)", base_out, base_zero, opt_out, opt_zero);
                end else begin
                    $display("[FAIL - MISMATCH] %s | Ctrl=%b, A=0x%08h, B=0x%08h", test_name, alu_ctrl, a, b);
                    $display("       Reference: Out=0x%08h, Zero=%b", ref_out, ref_zero);
                    $display("       Baseline : Out=0x%08h, Zero=%b", base_out, base_zero);
                    $display("       Optimized: Out=0x%08h, Zero=%b", opt_out, opt_zero);
                end
            end
        end
    endtask

    // Helper function for corner values with safe bit-masking and default return
    function [31:0] get_corner_val;
        input integer idx;
        begin
            get_corner_val = 32'h0000_0000;
            case (idx & 32'd7)
                0: get_corner_val = 32'h0000_0000;
                1: get_corner_val = 32'h0000_0001;
                2: get_corner_val = 32'hFFFF_FFFF; // -1
                3: get_corner_val = 32'h7FFF_FFFF; // Max signed positive
                4: get_corner_val = 32'h8000_0000; // Min signed negative
                5: get_corner_val = 32'hAAAA_AAAA;
                6: get_corner_val = 32'h5555_5555;
                7: get_corner_val = 32'h1234_5678;
                default: get_corner_val = 32'h0000_0000;
            endcase
        end
    endfunction

    integer i, j, op;

    initial begin
        $display("==================================================================");
        $display("   STARTING EXPANDED 32-BIT RISC-V (RV32I) ALU VERIFICATION       ");
        $display("   Testing: Baseline vs Optimized vs Independent Golden Model     ");
        $display("==================================================================");

        // --- 1. DIRECTED CORNER-CASE TESTS FOR EVERY OPCODE ---
        $display("[INFO] Running exhaustive corner-case combinations (1,024 vectors)...");

        for (op = 0; op < 16; op = op + 1) begin
            alu_ctrl = op[3:0];
            for (i = 0; i < 8; i = i + 1) begin
                for (j = 0; j < 8; j = j + 1) begin
                    a = get_corner_val(i);
                    b = get_corner_val(j);
                    apply_and_check("Corner Cross-Product");
                end
            end
        end

        // --- 2. DEDICATED BOUNDARY & SPECIALIZED TESTS ---
        $display("[INFO] Running specialized boundary checks (signed/unsigned/shifts)...");

        // Shift boundary tests: 0, 1, 30, 31, 32, 63, 0xFFFFFFFF
        alu_ctrl = 4'b0010; // SLL
        a = 32'h0000_0001; b = 32'd0;  apply_and_check("SLL by 0");
        a = 32'h0000_0001; b = 32'd1;  apply_and_check("SLL by 1");
        a = 32'h0000_0001; b = 32'd31; apply_and_check("SLL by 31 (MSB)");
        a = 32'h0000_0001; b = 32'd32; apply_and_check("SLL by 32 (wraps to 0)");
        a = 32'h0000_0001; b = 32'd63; apply_and_check("SLL by 63 (wraps to 31)");
        a = 32'hFFFF_FFFF; b = 32'hFFFF_FFFF; apply_and_check("SLL by 0xFFFFFFFF (wraps to 31)");

        alu_ctrl = 4'b0110; // SRL
        a = 32'h8000_0000; b = 32'd0;  apply_and_check("SRL by 0");
        a = 32'h8000_0000; b = 32'd1;  apply_and_check("SRL by 1");
        a = 32'h8000_0000; b = 32'd31; apply_and_check("SRL by 31 (LSB)");
        a = 32'h8000_0000; b = 32'd32; apply_and_check("SRL by 32 (wraps to 0)");

        alu_ctrl = 4'b0111; // SRA
        a = 32'h8000_0000; b = 32'd0;  apply_and_check("SRA negative by 0");
        a = 32'h8000_0000; b = 32'd1;  apply_and_check("SRA negative by 1 (sign ext)");
        a = 32'h8000_0000; b = 32'd31; apply_and_check("SRA negative by 31 (all 1s)");
        a = 32'h7FFF_FFFF; b = 32'd1;  apply_and_check("SRA positive by 1 (no sign ext)");
        a = 32'h7FFF_FFFF; b = 32'd31; apply_and_check("SRA positive by 31 (all 0s)");

        // SLT signed overflow tests
        alu_ctrl = 4'b0011; // SLT
        a = 32'h8000_0000; b = 32'h7FFF_FFFF; apply_and_check("SLT: MinNeg < MaxPos (TRUE)");
        a = 32'h7FFF_FFFF; b = 32'h8000_0000; apply_and_check("SLT: MaxPos < MinNeg (FALSE)");
        a = 32'hFFFF_FFFF; b = 32'h0000_0000; apply_and_check("SLT: -1 < 0 (TRUE)");
        a = 32'h0000_0000; b = 32'hFFFF_FFFF; apply_and_check("SLT: 0 < -1 (FALSE)");
        a = 32'hFFFF_FFFE; b = 32'hFFFF_FFFF; apply_and_check("SLT: -2 < -1 (TRUE)");
        a = 32'hFFFF_FFFF; b = 32'hFFFF_FFFE; apply_and_check("SLT: -1 < -2 (FALSE)");
        a = 32'h8000_0000; b = 32'h8000_0000; apply_and_check("SLT: Equal MinNeg (FALSE)");

        // SLTU unsigned boundary tests
        alu_ctrl = 4'b0100; // SLTU
        a = 32'h0000_0000; b = 32'hFFFF_FFFF; apply_and_check("SLTU: 0 < MaxUnsigned (TRUE)");
        a = 32'hFFFF_FFFF; b = 32'h0000_0000; apply_and_check("SLTU: MaxUnsigned < 0 (FALSE)");
        a = 32'h7FFF_FFFF; b = 32'h8000_0000; apply_and_check("SLTU: 0x7FFFFFFF < 0x80000000 (TRUE)");
        a = 32'h8000_0000; b = 32'h7FFF_FFFF; apply_and_check("SLTU: 0x80000000 < 0x7FFFFFFF (FALSE)");
        a = 32'hFFFF_FFFF; b = 32'hFFFF_FFFF; apply_and_check("SLTU: Equal MaxUnsigned (FALSE)");

        // ADD / SUB overflow tests
        alu_ctrl = 4'b0000; // ADD
        a = 32'h7FFF_FFFF; b = 32'h0000_0001; apply_and_check("ADD: Signed overflow to 0x80000000");
        a = 32'hFFFF_FFFF; b = 32'h0000_0001; apply_and_check("ADD: Unsigned overflow wraps to 0");
        a = 32'h8000_0000; b = 32'h8000_0000; apply_and_check("ADD: Two MinNeg wraps to 0");

        alu_ctrl = 4'b0001; // SUB
        a = 32'h0000_0000; b = 32'h0000_0001; apply_and_check("SUB: 0 - 1 wraps to 0xFFFFFFFF");
        a = 32'h8000_0000; b = 32'h0000_0001; apply_and_check("SUB: MinNeg - 1 overflows to MaxPos");

        // --- 3. PSEUDO-RANDOM EXTENSIVE STRESS TESTING ---
        $display("[INFO] Running 5,000 randomized test vectors genuinely exercising all operations...");
        for (i = 0; i < 5000; i = i + 1) begin
            // 20% of the time, bias toward corner values; 80% uniform random
            if ((i % 5) == 0) begin
                a = get_corner_val($random);
            end else begin
                a = {$random, $random};
            end

            if ((i % 5) == 1) begin
                b = get_corner_val($random);
            end else begin
                b = {$random, $random};
            end

            // Genuinely exercise every supported operation:
            // 4,500 tests (90%) thoroughly test all 10 supported operations (each gets exactly 450 tests)
            // 500 tests (10%) test default/invalid opcode space (10..15)
            if (i < 4500) begin
                alu_ctrl = (i % 10);
            end else begin
                alu_ctrl = 4'd10 + ((i - 4500) % 6);
            end

            apply_and_check("Random Stress Vector");
        end

        // --- 4. SEPARATE DEDICATED SWITCHING-ACTIVITY WORKLOAD PROFILING ---
        $display("[INFO] Executing dedicated switching-activity workload profiling trace (100 cycles)...");
        // Settle initial state prior to measurement window to exclude initialization transitions
        a = 32'hA5A5_A5A5;
        b = 32'h5A5A_5A5A;
        alu_ctrl = 4'b0000;
        #10;

`ifdef DUMP_VCD
        $dumpfile("reports/riscv_activity.vcd");
        $dumpvars(0, riscv_alu_tb);
`endif

        for (i = 0; i < 100; i = i + 1) begin
            // Controlled, alternating instruction sequence applied identically to both DUTs
            case (i % 5)
                0: alu_ctrl = 4'b1001; // AND (Logic)
                1: alu_ctrl = 4'b1000; // OR  (Logic)
                2: alu_ctrl = 4'b0101; // XOR (Logic)
                3: alu_ctrl = 4'b0000; // ADD (Arithmetic)
                4: alu_ctrl = 4'b0010; // SLL (Shift)
            endcase
            a = a ^ (32'h0101_0101 * (i + 1));
            b = b + (32'h0202_0202 * (i + 1));
            #10;
        end

`ifdef DUMP_VCD
        $dumpoff;
`endif
        #10;

        // --- 5. FINAL SUMMARY ---
        $display("==================================================================");
        $display(" 32-BIT RISC-V ALU VERIFICATION: Total=%0d, Passed=%0d, Failed=%0d", 
                 (pass_count + fail_count), pass_count, fail_count);
        $display("==================================================================");

        if (fail_count == 0) begin
            $display("[SIMULATION STATUS] ALL 32-BIT RISC-V TESTS PASSED SUCCESSFULLY!");
            $finish;
        end else begin
            $display("[SIMULATION STATUS] VERIFICATION FAILED with %0d mismatches!", fail_count);
            $fatal(1, "32-bit RISC-V ALU verification failed.");
        end
    end

endmodule
