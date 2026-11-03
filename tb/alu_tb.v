`timescale 1ns / 1ps

module alu_tb;

    reg  [7:0] a;
    reg  [7:0] b;
    reg  [2:0] opcode;
    wire [7:0] alu_out;
    wire       carry_out;
    wire       zero;

    // Instantiate Device Under Test (DUT)
`ifdef TEST_OPTIMIZED
    alu_optimized dut (
        .a(a),
        .b(b),
        .opcode(opcode),
        .alu_out(alu_out),
        .carry_out(carry_out),
        .zero(zero)
    );
`else
    alu_baseline dut (
        .a(a),
        .b(b),
        .opcode(opcode),
        .alu_out(alu_out),
        .carry_out(carry_out),
        .zero(zero)
    );
`endif

    integer pass_count = 0;
    integer fail_count = 0;

    task check_result;
        input [7:0] expected_out;
        input       expected_carry;
        input [255:0] test_name;
        begin
            #5; // Wait for combinational propagation
            if (alu_out === expected_out && carry_out === expected_carry && zero === (expected_out == 8'b0)) begin
                pass_count = pass_count + 1;
                $display("[PASS] %s | Op: %b, A: 0x%02h, B: 0x%02h -> Out: 0x%02h (Carry: %b, Zero: %b)",
                         test_name, opcode, a, b, alu_out, carry_out, zero);
            end else begin
                fail_count = fail_count + 1;
                $display("[FAIL] %s | Op: %b, A: 0x%02h, B: 0x%02h | Expected: Out=0x%02h, C=%b, Z=%b | Got: Out=0x%02h, C=%b, Z=%b",
                         test_name, opcode, a, b, expected_out, expected_carry, (expected_out == 8'b0), alu_out, carry_out, zero);
            end
        end
    endtask

    initial begin
        $display("==================================================");
`ifdef TEST_OPTIMIZED
        $display("       STARTING SIMULATION FOR ALU_OPTIMIZED      ");
`else
        $display("       STARTING SIMULATION FOR ALU_BASELINE       ");
`endif
        $display("==================================================");

        // --- TEST ADD (3'b000) ---
        opcode = 3'b000;
        a = 8'h05; b = 8'h03; check_result(8'h08, 1'b0, "ADD Basic (5 + 3)");
        a = 8'hFF; b = 8'h01; check_result(8'h00, 1'b1, "ADD Overflow (255 + 1)");
        a = 8'h00; b = 8'h00; check_result(8'h00, 1'b0, "ADD Zeros (0 + 0)");
        a = 8'h7F; b = 8'h01; check_result(8'h80, 1'b0, "ADD Boundary (127 + 1)");

        // --- TEST SUB (3'b001) ---
        opcode = 3'b001;
        a = 8'h0A; b = 8'h04; check_result(8'h06, 1'b0, "SUB Basic (10 - 4)");
        a = 8'h04; b = 8'h0A; check_result(8'hFA, 1'b1, "SUB Underflow (4 - 10)");
        a = 8'h55; b = 8'h55; check_result(8'h00, 1'b0, "SUB Equal (85 - 85)");
        a = 8'hFF; b = 8'h01; check_result(8'hFE, 1'b0, "SUB High (255 - 1)");

        // --- TEST AND (3'b010) ---
        opcode = 3'b010;
        a = 8'hFF; b = 8'h0F; check_result(8'h0F, 1'b0, "AND Mask (0xFF & 0x0F)");
        a = 8'hAA; b = 8'h55; check_result(8'h00, 1'b0, "AND Complementary (0xAA & 0x55)");
        a = 8'hF0; b = 8'hA5; check_result(8'hA0, 1'b0, "AND Mixed (0xF0 & 0xA5)");

        // --- TEST OR (3'b011) ---
        opcode = 3'b011;
        a = 8'hF0; b = 8'h0F; check_result(8'hFF, 1'b0, "OR Combine (0xF0 | 0x0F)");
        a = 8'hAA; b = 8'h55; check_result(8'hFF, 1'b0, "OR Alternating (0xAA | 0x55)");
        a = 8'h00; b = 8'h00; check_result(8'h00, 1'b0, "OR Zeros (0x00 | 0x00)");

        // --- TEST XOR (3'b100) ---
        opcode = 3'b100;
        a = 8'hFF; b = 8'hAA; check_result(8'h55, 1'b0, "XOR Inversion (0xFF ^ 0xAA)");
        a = 8'hA5; b = 8'hA5; check_result(8'h00, 1'b0, "XOR Self (0xA5 ^ 0xA5)");
        a = 8'h12; b = 8'h34; check_result(8'h26, 1'b0, "XOR Arbitrary (0x12 ^ 0x34)");

        // --- SUMMARY ---
        $display("==================================================");
        $display(" TESTS COMPLETED: Total=%0d, Passed=%0d, Failed=%0d", 
                 (pass_count + fail_count), pass_count, fail_count);
        $display("==================================================");

        if (fail_count == 0) begin
            $display("[SIMULATION STATUS] ALL TESTS PASSED!");
        end else begin
            $display("[SIMULATION STATUS] VERIFICATION FAILED with %0d errors!", fail_count);
        end
        $finish;
    end

endmodule
