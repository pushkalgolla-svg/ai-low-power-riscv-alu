`timescale 1ns / 1ps

module riscv_alu_tb;

    reg  [31:0] a;
    reg  [31:0] b;
    reg  [3:0]  alu_ctrl;
    wire [31:0] alu_out;
    wire        zero;

`ifdef TEST_OPTIMIZED
    riscv_alu_optimized dut (
        .a(a),
        .b(b),
        .alu_ctrl(alu_ctrl),
        .alu_out(alu_out),
        .zero(zero)
    );
`else
    riscv_alu_baseline dut (
        .a(a),
        .b(b),
        .alu_ctrl(alu_ctrl),
        .alu_out(alu_out),
        .zero(zero)
    );
`endif

    integer pass_count = 0;
    integer fail_count = 0;

    task check_result;
        input [31:0] expected_out;
        input [255:0] test_name;
        begin
            #10;
            if (alu_out === expected_out && zero === (expected_out == 32'b0)) begin
                pass_count = pass_count + 1;
                $display("[PASS] %s | Ctrl: %b, A: 0x%08h, B: 0x%08h -> Out: 0x%08h (Zero: %b)",
                         test_name, alu_ctrl, a, b, alu_out, zero);
            end else begin
                fail_count = fail_count + 1;
                $display("[FAIL] %s | Ctrl: %b, A: 0x%08h, B: 0x%08h | Expected: 0x%08h (Z=%b) | Got: 0x%08h (Z=%b)",
                         test_name, alu_ctrl, a, b, expected_out, (expected_out == 32'b0), alu_out, zero);
            end
        end
    endtask

    integer i;

    initial begin
`ifdef DUMP_VCD
    `ifdef TEST_OPTIMIZED
        $dumpfile("reports/riscv_optimized_activity.vcd");
    `else
        $dumpfile("reports/riscv_baseline_activity.vcd");
    `endif
        $dumpvars(0, dut);
`endif

        $display("==================================================================");
`ifdef TEST_OPTIMIZED
        $display("       STARTING SIMULATION FOR RISC-V 32-bit ALU (OPTIMIZED)      ");
`else
        $display("       STARTING SIMULATION FOR RISC-V 32-bit ALU (BASELINE)       ");
`endif
        $display("==================================================================");

        // 1. ADD
        alu_ctrl = 4'b0000;
        a = 32'h0000_0005; b = 32'h0000_0003; check_result(32'h0000_0008, "ADD Basic");
        a = 32'hFFFF_FFFF; b = 32'h0000_0001; check_result(32'h0000_0000, "ADD Overflow (Zero)");
        a = 32'h7FFF_FFFF; b = 32'h0000_0001; check_result(32'h8000_0000, "ADD Signed Overflow");

        // 2. SUB
        alu_ctrl = 4'b0001;
        a = 32'h0000_000A; b = 32'h0000_0004; check_result(32'h0000_0006, "SUB Basic");
        a = 32'h0000_0000; b = 32'h0000_0001; check_result(32'hFFFF_FFFF, "SUB Negative (-1)");
        a = 32'h1234_5678; b = 32'h1234_5678; check_result(32'h0000_0000, "SUB Equal (Zero)");

        // 3. SLL (Shift Left Logical)
        alu_ctrl = 4'b0010;
        a = 32'h0000_0001; b = 32'd4; check_result(32'h0000_0010, "SLL by 4");
        a = 32'h0000_0001; b = 32'd31; check_result(32'h8000_0000, "SLL to MSB (by 31)");
        a = 32'hFFFF_FFFF; b = 32'd32; check_result(32'hFFFF_FFFF, "SLL shamt[4:0] mask (by 32 => 0)");

        // 4. SLT (Set Less Than, Signed)
        alu_ctrl = 4'b0011;
        a = 32'hFFFF_FFFF; b = 32'h0000_0001; check_result(32'd1, "SLT (-1 < 1 -> 1)");
        a = 32'h0000_0005; b = 32'h0000_0002; check_result(32'd0, "SLT (5 < 2 -> 0)");
        a = 32'h8000_0000; b = 32'h7FFF_FFFF; check_result(32'd1, "SLT (MinNegative < MaxPositive)");

        // 5. SLTU (Set Less Than, Unsigned)
        alu_ctrl = 4'b0100;
        a = 32'h0000_0001; b = 32'hFFFF_FFFF; check_result(32'd1, "SLTU (1 < 0xFFFFFFFF -> 1)");
        a = 32'hFFFF_FFFF; b = 32'h0000_0001; check_result(32'd0, "SLTU (0xFFFFFFFF < 1 -> 0)");

        // 6. XOR
        alu_ctrl = 4'b0101;
        a = 32'hFFFF_0000; b = 32'h0000_FFFF; check_result(32'hFFFF_FFFF, "XOR Alternate");
        a = 32'hA5A5_A5A5; b = 32'hA5A5_A5A5; check_result(32'h0000_0000, "XOR Self (Zero)");

        // 7. SRL (Shift Right Logical)
        alu_ctrl = 4'b0110;
        a = 32'h8000_0000; b = 32'd4; check_result(32'h0800_0000, "SRL Zero-fill");
        a = 32'hFFFF_FFFF; b = 32'd8; check_result(32'h00FF_FFFF, "SRL by 8");

        // 8. SRA (Shift Right Arithmetic)
        alu_ctrl = 4'b0111;
        a = 32'h8000_0000; b = 32'd4; check_result(32'hF800_0000, "SRA Sign-extension");
        a = 32'h7FFF_FFFF; b = 32'd4; check_result(32'h07FF_FFFF, "SRA Positive no-sign-ext");

        // 9. OR & 10. AND
        alu_ctrl = 4'b1000;
        a = 32'h1234_0000; b = 32'h0000_5678; check_result(32'h1234_5678, "OR Basic");
        alu_ctrl = 4'b1001;
        a = 32'hFFFF_5678; b = 32'h0000_FFFF; check_result(32'h0000_5678, "AND Basic");

        // --- Workload Loop (Simulating continuous logical & arithmetic operations to measure switching power) ---
        $display("[INFO] Running switching activity workload profile...");
        for (i = 0; i < 50; i = i + 1) begin
            #5;
            alu_ctrl = (i % 2 == 0) ? 4'b1001 : 4'b1000; // Toggle AND and OR operations
            a = a ^ (32'h0101_0101 * (i + 1));
            b = b + (32'h0202_0202 * (i + 1));
        end

        // --- SUMMARY ---
        $display("==================================================================");
        $display(" TESTS COMPLETED: Total=%0d, Passed=%0d, Failed=%0d", 
                 (pass_count + fail_count), pass_count, fail_count);
        $display("==================================================================");

        if (fail_count == 0) begin
            $display("[SIMULATION STATUS] ALL RISC-V 32-BIT ALU TESTS PASSED!");
        end else begin
            $display("[SIMULATION STATUS] VERIFICATION FAILED with %0d errors!", fail_count);
        end
        $finish;
    end

endmodule
