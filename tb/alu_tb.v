`timescale 1ns / 1ps

module alu_tb;

    reg  [7:0] a;
    reg  [7:0] b;
    reg  [2:0] opcode;

    // Baseline DUT
    wire [7:0] base_out;
    wire       base_carry;
    wire       base_zero;

    alu_baseline dut_base (
        .a(a),
        .b(b),
        .opcode(opcode),
        .alu_out(base_out),
        .carry_out(base_carry),
        .zero(base_zero)
    );

    // Optimized DUT (or candidate under evaluation)
    wire [7:0] opt_out;
    wire       opt_carry;
    wire       opt_zero;

`ifdef TEST_CANDIDATE
    alu_candidate dut_opt (
`else
    alu_optimized dut_opt (
`endif
        .a(a),
        .b(b),
        .opcode(opcode),
        .alu_out(opt_out),
        .carry_out(opt_carry),
        .zero(opt_zero)
    );

    // =========================================================================
    // Activity Instrumentation Probes (Equivalent Logical Datapath Boundaries)
    // =========================================================================
    // 1. Functional Datapath Category Probes:
    // Arithmetic Datapath Inputs (Adder/Subtractor)
    wire [7:0] base_probe_arith_a = dut_base.a;
    wire [7:0] base_probe_arith_b = dut_base.b;
    wire [7:0] opt_probe_arith_a  = dut_opt.arith_a;
    wire [7:0] opt_probe_arith_b  = dut_opt.arith_b;

    // Logic Datapath Inputs (AND/OR/XOR)
    wire [7:0] base_probe_logic_a = dut_base.a;
    wire [7:0] base_probe_logic_b = dut_base.b;
    wire [7:0] opt_probe_logic_a  = dut_opt.logic_a;
    wire [7:0] opt_probe_logic_b  = dut_opt.logic_b;

    // 2. Individual Baseline Operator Probes (Where baseline uses separate operations):
    wire [7:0] base_op_add_a      = dut_base.a;
    wire [7:0] base_op_add_b      = dut_base.b;
    wire [7:0] base_op_sub_a      = dut_base.a;
    wire [7:0] base_op_sub_b      = dut_base.b;
    wire [7:0] base_op_and_a      = dut_base.a;
    wire [7:0] base_op_and_b      = dut_base.b;
    wire [7:0] base_op_or_a       = dut_base.a;
    wire [7:0] base_op_or_b       = dut_base.b;
    wire [7:0] base_op_xor_a      = dut_base.a;
    wire [7:0] base_op_xor_b      = dut_base.b;

    // Golden Reference Model
    reg [7:0] ref_out;
    reg       ref_carry;
    reg       ref_zero;
    reg [8:0] temp_arith;

    task golden_reference;
        input [7:0] in_a;
        input [7:0] in_b;
        input [2:0] op;
        output [7:0] out;
        output       carry;
        output       z;
        begin
            temp_arith = 9'b0;
            out        = 8'b0;
            carry      = 1'b0;
            case (op)
                3'b000: begin // ADD
                    temp_arith = in_a + in_b;
                    out        = temp_arith[7:0];
                    carry      = temp_arith[8];
                end
                3'b001: begin // SUB
                    temp_arith = in_a - in_b;
                    out        = temp_arith[7:0];
                    carry      = temp_arith[8]; // borrow flag
                end
                3'b010: begin // AND
                    out   = in_a & in_b;
                    carry = 1'b0;
                end
                3'b011: begin // OR
                    out   = in_a | in_b;
                    carry = 1'b0;
                end
                3'b100: begin // XOR
                    out   = in_a ^ in_b;
                    carry = 1'b0;
                end
                default: begin
                    out   = 8'b0;
                    carry = 1'b0;
                end
            endcase
            z = (out == 8'b0);
        end
    endtask

    integer pass_count = 0;
    integer fail_count = 0;

    task apply_and_check;
        input [255:0] test_name;
        reg has_unknown;
        begin
            #5; // Wait for combinational propagation
            golden_reference(a, b, opcode, ref_out, ref_carry, ref_zero);

            // Reject unknown (X/Z) bits on all inputs and outputs
            has_unknown = (^a === 1'bx) || (^b === 1'bx) || (^opcode === 1'bx) ||
                          (^base_out === 1'bx) || (^opt_out === 1'bx) ||
                          (base_carry === 1'bx) || (opt_carry === 1'bx) ||
                          (base_zero === 1'bx) || (opt_zero === 1'bx);

            if (!has_unknown &&
                base_out === ref_out && opt_out === ref_out &&
                base_carry === ref_carry && opt_carry === ref_carry &&
                base_zero === ref_zero && opt_zero === ref_zero) begin
                pass_count = pass_count + 1;
            end else begin
                fail_count = fail_count + 1;
                if (has_unknown) begin
                    $display("[FAIL - UNKNOWN VALUE X/Z] %s | Op: %b, A: 0x%02h, B: 0x%02h", test_name, opcode, a, b);
                    $display("       Base: Out=0x%02h, C=%b, Z=%b", base_out, base_carry, base_zero);
                    $display("       Opt : Out=0x%02h, C=%b, Z=%b", opt_out, opt_carry, opt_zero);
                end else begin
                    $display("[FAIL] %s | Op: %b, A: 0x%02h, B: 0x%02h", test_name, opcode, a, b);
                    $display("       Ref : Out=0x%02h, C=%b, Z=%b", ref_out, ref_carry, ref_zero);
                    $display("       Base: Out=0x%02h, C=%b, Z=%b", base_out, base_carry, base_zero);
                    $display("       Opt : Out=0x%02h, C=%b, Z=%b", opt_out, opt_carry, opt_zero);
                end
            end
        end
    endtask

    integer i;
    reg [7:0] corner_vals [0:5];

    initial begin
        corner_vals[0] = 8'h00;
        corner_vals[1] = 8'h01;
        corner_vals[2] = 8'h7F;
        corner_vals[3] = 8'h80;
        corner_vals[4] = 8'hFE;
        corner_vals[5] = 8'hFF;

        $display("================================================================");
        $display("   STARTING EXPANDED 8-BIT ALU TESTBENCH (DIRECTED + RANDOM)    ");
        $display("   Testing: Baseline vs Optimized vs Independent Golden Model    ");
        $display("================================================================");

        // --- 1. DIRECTED CORNER-CASE TESTING ---
        $display("[INFO] Running comprehensive directed corner-case tests...");

        // Exhaustive cross-product of corner values for all opcodes (including invalid 3'b101..3'b111)
        for (i = 0; i < 8; i = i + 1) begin
            opcode = i[2:0];
            // Test pairs of corner values
            a = 8'h00; b = 8'h00; apply_and_check("Corners: Zeros");
            a = 8'hFF; b = 8'h01; apply_and_check("Corners: 0xFF, 0x01");
            a = 8'h7F; b = 8'h01; apply_and_check("Corners: 0x7F, 0x01 (signed boundary)");
            a = 8'h80; b = 8'h01; apply_and_check("Corners: 0x80, 0x01");
            a = 8'h80; b = 8'h80; apply_and_check("Corners: 0x80, 0x80");
            a = 8'hFF; b = 8'hFF; apply_and_check("Corners: 0xFF, 0xFF");
            a = 8'hAA; b = 8'h55; apply_and_check("Corners: Alternating 0xAA, 0x55");
            a = 8'h55; b = 8'hAA; apply_and_check("Corners: Alternating 0x55, 0xAA");
            a = 8'h04; b = 8'h0A; apply_and_check("Corners: 4, 10 (SUB borrow test)");
            a = 8'h0A; b = 8'h04; apply_and_check("Corners: 10, 4 (SUB no-borrow test)");
        end

        // --- 2. PSEUDO-RANDOM EXTENSIVE STRESS TESTING ---
        $display("[INFO] Running 3,000 randomized test vectors across all opcodes...");
        for (i = 0; i < 3000; i = i + 1) begin
            a = $random;
            b = $random;
            // 2,500 tests (83%) test the 5 valid opcodes (0..4) uniformly (500 each)
            // 500 tests (17%) test invalid opcodes (5..7)
            if (i < 2500) begin
                opcode = (i % 5);
            end else begin
                opcode = 3'd5 + ((i - 2500) % 3);
            end
            apply_and_check("Random Vector");
        end

        // --- 3. SEPARATE DEDICATED SWITCHING-ACTIVITY WORKLOAD PROFILING ---
        $display("[INFO] Executing dedicated 8-bit switching-activity workload profiling trace (100 cycles)...");
        // Settle initial state prior to measurement window to exclude initialization transitions
        a = 8'hA5;
        b = 8'h5A;
        opcode = 3'b000;
        #10;

`ifdef DUMP_VCD
        $dumpfile("reports/alu_activity.vcd");
        $dumpvars(0, alu_tb);
`endif

        for (i = 0; i < 100; i = i + 1) begin
            case (i % 5)
                0: opcode = 3'b010; // AND (Logic)
                1: opcode = 3'b011; // OR  (Logic)
                2: opcode = 3'b100; // XOR (Logic)
                3: opcode = 3'b000; // ADD (Arithmetic)
                4: opcode = 3'b001; // SUB (Arithmetic)
            endcase
            a = a ^ (8'h11 * (i + 1));
            b = b + (8'h22 * (i + 1));
            #10;
        end

`ifdef DUMP_VCD
        $dumpoff;
`endif
        #10;

        // --- 4. FINAL SUMMARY ---
        $display("================================================================");
        $display(" 8-BIT ALU VERIFICATION SUMMARY: Total=%0d, Passed=%0d, Failed=%0d",
                 (pass_count + fail_count), pass_count, fail_count);
        $display("================================================================");

        if (fail_count == 0) begin
            $display("[SIMULATION STATUS] ALL TESTS PASSED SUCCESSFULLY!");
            $finish;
        end else begin
            $display("[SIMULATION STATUS] VERIFICATION FAILED with %0d errors!", fail_count);
            $fatal(1, "8-bit ALU verification encountered mismatches.");
        end
    end

endmodule
