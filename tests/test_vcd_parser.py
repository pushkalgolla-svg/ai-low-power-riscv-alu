"""
Unit Tests for VCD Switching-Activity Parser
--------------------------------------------
Validates:
1. Vector transitions (multi-bit toggles).
2. Scalar transitions (1-bit signals).
3. Initial values (ensuring $dumpvars is not counted as transitions).
4. Width changes / unpadded vector handling.
5. Multiple hierarchy scopes (exact path resolution without alias collision).
6. Unknown values (handling 'x' and 'z' cleanly).
7. Missing signals (safe query handling).
"""

import unittest
from pathlib import Path
import sys

# Ensure scripts dir is on sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from vcd_parser import VCDParser


class TestVCDParser(unittest.TestCase):

    def test_initial_values_not_counted(self):
        """Verifies that initial values inside $dumpvars do NOT count as transitions."""
        vcd_content = """$date today $end
$version test $end
$timescale 1ns $end
$scope module top $end
$var wire 8 ! vec [7:0] $end
$var wire 1 " clk $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
b10101010 !
0"
$end
#10
"""
        parser = VCDParser()
        parser.parse(vcd_text=vcd_content)
        self.assertEqual(parser.get_transitions("top.vec"), 0)
        self.assertEqual(parser.get_transitions("top.clk"), 0)

    def test_vector_transitions(self):
        """Verifies correct bit-by-bit transition counting on vectors."""
        vcd_content = """$date today $end
$timescale 1ns $end
$scope module top $end
$var wire 8 ! data [7:0] $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
b00000000 !
$end
#10
b11111111 !
#20
b11110000 !
#30
b11110000 !
#40
b00001111 !
"""
        parser = VCDParser()
        parser.parse(vcd_text=vcd_content)
        # #10: 00000000 -> 11111111 (8 toggles)
        # #20: 11111111 -> 11110000 (4 toggles: bits [3:0] 1->0)
        # #30: 11110000 -> 11110000 (0 toggles: same value)
        # #40: 11110000 -> 00001111 (8 toggles: bits [7:4] 1->0, bits [3:0] 0->1)
        # Total = 8 + 4 + 0 + 8 = 20 toggles
        self.assertEqual(parser.get_transitions("top.data"), 20)

    def test_scalar_transitions(self):
        """Verifies correct transition counting for 1-bit scalar signals."""
        vcd_content = """$timescale 1ns $end
$scope module tb $end
$var wire 1 % rst_n $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0%
$end
#10
1%
#20
1%
#30
0%
"""
        parser = VCDParser()
        parser.parse(vcd_text=vcd_content)
        # 0 -> 1 (1 toggle), 1 -> 1 (0 toggles), 1 -> 0 (1 toggle). Total = 2.
        self.assertEqual(parser.get_transitions("tb.rst_n"), 2)

    def test_width_changes_and_normalization(self):
        """Verifies that VCD vectors with varying leading zeros are normalized to declared width."""
        vcd_content = """$timescale 1ns $end
$scope module tb $end
$var wire 8 # val [7:0] $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
b0 #
$end
#10
b1 #
#20
b11 #
#30
b101 #
"""
        parser = VCDParser()
        parser.parse(vcd_text=vcd_content)
        # Initial: 00000000
        # #10: b1 -> 00000001 (1 toggle: bit 0 from 0->1)
        # #20: b11 -> 00000011 (1 toggle: bit 1 from 0->1, bit 0 unchanged)
        # #30: b101 -> 00000101 (1 toggle: bit 2 from 0->1, bit 1 from 1->0: wait!
        #      prev: 00000011, curr: 00000101 -> bit 0 (1->1: 0), bit 1 (1->0: 1), bit 2 (0->1: 1) = 2 toggles)
        # Total = 1 + 1 + 2 = 4 toggles
        self.assertEqual(parser.get_transitions("tb.val"), 4)

    def test_multiple_hierarchy_scopes(self):
        """Verifies exact hierarchical path matching without suffix collisions or cross-talk."""
        vcd_content = """$timescale 1ns $end
$scope module tb $end
  $var wire 32 A a [31:0] $end
  $scope module dut_base $end
    $var wire 32 B a [31:0] $end
  $upscope $end
  $scope module dut_opt $end
    $var wire 32 C a [31:0] $end
  $upscope $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
b0000 A
b0000 B
b0000 C
$end
#10
b1111 A
#20
b0011 B
#30
b0101 C
"""
        parser = VCDParser()
        parser.parse(vcd_text=vcd_content)
        # tb.a: 0000 -> 1111 = 4 toggles
        # tb.dut_base.a: 0000 -> 0011 = 2 toggles
        # tb.dut_opt.a: 0000 -> 0101 = 2 toggles
        self.assertEqual(parser.get_transitions("tb.a"), 4)
        self.assertEqual(parser.get_transitions("tb.dut_base.a"), 2)
        self.assertEqual(parser.get_transitions("tb.dut_opt.a"), 2)

    def test_unknown_values(self):
        """Verifies that unknown bits (x/z) do not crash the parser and are excluded from 0<->1 switching."""
        vcd_content = """$timescale 1ns $end
$scope module tb $end
$var wire 4 & sig [3:0] $end
$var wire 1 * flag $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
bxxxx &
x*
$end
#10
b10xz &
0*
#20
b0100 &
1*
"""
        parser = VCDParser()
        parser.parse(vcd_text=vcd_content)
        # #10: sig from xxxx to 10xz -> no valid 0<->1 toggles (prior state was all x)
        #      flag from x to 0 -> no valid 0<->1 toggle
        # #20: sig from 10xz to 0100:
        #      bit 3: 1 -> 0 (1 toggle)
        #      bit 2: 0 -> 1 (1 toggle)
        #      bit 1: x -> 0 (not a 0<->1 toggle)
        #      bit 0: z -> 0 (not a 0<->1 toggle)
        #      Total for sig = 2 toggles
        #      flag: 0 -> 1 (1 toggle)
        self.assertEqual(parser.get_transitions("tb.sig"), 2)
        self.assertEqual(parser.get_transitions("tb.flag"), 1)

    def test_missing_signals(self):
        """Verifies that querying a signal not present in the VCD returns 0 safely."""
        vcd_content = """$timescale 1ns $end
$scope module tb $end
$var wire 1 ! clk $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
$end
#10
1!
"""
        parser = VCDParser()
        parser.parse(vcd_text=vcd_content)
        self.assertEqual(parser.get_transitions("tb.non_existent_signal"), 0)
        self.assertFalse(parser.has_signal("tb.non_existent_signal"))
        self.assertTrue(parser.has_signal("tb.clk"))

    def test_time_window_filtering(self):
        """Verifies that start_time and end_time restrict the counted transitions."""
        vcd_content = """$timescale 1ns $end
$scope module tb $end
$var wire 1 ! clk $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
$end
#10
1!
#20
0!
#30
1!
#40
0!
#50
1!
"""
        # Without window: 5 toggles
        p_all = VCDParser()
        p_all.parse(vcd_text=vcd_content)
        self.assertEqual(p_all.get_transitions("tb.clk"), 5)

        # Window [20, 40]: only events at #20, #30, #40 counted (3 toggles)
        p_win = VCDParser(start_time=20, end_time=40)
        p_win.parse(vcd_text=vcd_content)
        self.assertEqual(p_win.get_transitions("tb.clk"), 3)


if __name__ == "__main__":
    unittest.main()
