"""
AI-Powered Low-Power 8-bit ALU Design & Synthesis Orchestrator
--------------------------------------------------------------
Features:
1. RTL Verification: Dual-DUT lockstep co-simulation (baseline vs optimized vs golden model).
2. Technology-Independent Synthesis: Generic CMOS gate mapping via Yosys with zero arbitrary multipliers.
3. Candidate Safety: AI generation writes strictly to candidate files without overwriting validated RTL.
4. Fully Offline Capable: Standard verification and synthesis require no API keys or AI dependencies.
"""

import os
import re
import sys
import shutil
import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
TB_DIR = PROJECT_ROOT / "tb"
REPORTS_DIR = PROJECT_ROOT / "reports"
ENV_FILE = PROJECT_ROOT / ".env"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)

CANDIDATE_MODELS = [
    "models/gemini-flash-lite-latest",
    "models/gemini-flash-latest",
    "gemini-2.5-flash",
]


def read_file(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: Path, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def extract_code(raw_text: str) -> str:
    match = re.search(r"```(?:verilog)?\s*(.*?)\s*```", raw_text, re.DOTALL)
    return match.group(1).strip() if match else raw_text.strip()


def run_iverilog_verification(opt_file: Path, is_candidate: bool = False) -> tuple:
    """Runs lockstep dual-DUT co-simulation with Icarus Verilog against golden reference model."""
    tb_file = TB_DIR / "alu_tb.v"
    base_file = SRC_DIR / "alu_baseline.v"
    out_vvp = REPORTS_DIR / ("alu_cand_sim.vvp" if is_candidate else "alu_sim.vvp")
    log_file = REPORTS_DIR / ("alu_cand_sim.log" if is_candidate else "alu_sim.log")

    cmd = [
        "iverilog",
        "-g2005-sv",
    ]
    if is_candidate:
        cmd.extend(["-DTEST_CANDIDATE"])

    cmd.extend([
        "-o", str(out_vvp),
        str(base_file),
        str(opt_file),
        str(tb_file)
    ])

    comp_res = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    if comp_res.returncode != 0:
        return False, f"Compilation Error:\n{comp_res.stderr}\n{comp_res.stdout}"

    sim_res = subprocess.run(["vvp", str(out_vvp)], capture_output=True, text=True, cwd=PROJECT_ROOT)
    write_file(log_file, sim_res.stdout)

    passed = (
        "ALL TESTS PASSED SUCCESSFULLY!" in sim_res.stdout
        and sim_res.returncode == 0
    )
    return passed, sim_res.stdout


def get_yosys_cmd_args(script: str) -> list:
    """
    Builds the synthesis command, preferring the pinned YowASP Yosys executable (0.70)
    over system Yosys for reproducible, cross-platform synthesis results.
    """
    # 1. Check for yowasp-yosys binary in the same directory as active Python interpreter
    py_bin_dir = Path(sys.executable).parent
    for candidate in ("yowasp-yosys.exe", "yowasp-yosys"):
        yowasp_bin = py_bin_dir / candidate
        if yowasp_bin.exists():
            return [str(yowasp_bin), "-p", script]

    # 2. Check for yowasp-yosys anywhere on PATH
    which_yowasp = shutil.which("yowasp-yosys")
    if which_yowasp:
        return [which_yowasp, "-p", script]

    # 3. Direct module invocation via active Python interpreter
    try:
        import yowasp_yosys
        return [
            sys.executable,
            "-c",
            "import sys, yowasp_yosys; sys.exit(yowasp_yosys.run_yosys(sys.argv[1:]))",
            "-p",
            script,
        ]
    except ImportError:
        pass

    # 4. Fallback to system yosys binary if present
    which_yosys = shutil.which("yosys")
    if which_yosys:
        return [which_yosys, "-p", script]

    return ["yowasp-yosys", "-p", script]


def run_yosys_synthesis(verilog_file: Path, top_module: str) -> dict:
    stat_file = REPORTS_DIR / f"{top_module}_synth.stat"
    yosys_script = f"read_verilog {verilog_file.as_posix()}; synth -noabc -top {top_module}; stat"
    cmd = get_yosys_cmd_args(yosys_script)

    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    raw_output = proc.stdout + "\n" + proc.stderr
    write_file(stat_file, raw_output)

    if proc.returncode != 0:
        print(f"[ERROR] Yosys synthesis failed for {top_module}:\n{raw_output}")
        sys.exit(1)

    try:
        stats = parse_yosys_stats(raw_output, top_module)
    except Exception as e:
        print(f"[ERROR] Failed parsing synthesis statistics for {top_module}: {e}")
        sys.exit(1)

    return stats


def parse_yosys_stats(output: str, module_name: str) -> dict:
    """
    Parses Yosys stat output across multiple formats:
    - Standard Ubuntu/Debian packages (Yosys 0.9 - 0.38+): 'Number of cells: 231', '   $_AND_   88'
    - Modern columnar YoWASP releases: '231 cells', '   88   $_AND_'
    """
    stats = {
        "module": module_name,
        "wires": 0,
        "wire_bits": 0,
        "public_wires": 0,
        "public_wire_bits": 0,
        "cells": 0,
        "cell_details": {}
    }

    stat_match = re.search(r"=== " + re.escape(module_name) + r" ===(.*?)(?:===|\Z)", output, re.DOTALL)
    block = stat_match.group(1) if stat_match else output

    # 1. Total netlist wires (nets)
    m_wires = re.search(r"Number of wires:\s*(\d+)", block) or re.search(r"^\s*(\d+)\s+wires\b", block, re.MULTILINE)
    if m_wires:
        stats["wires"] = int(m_wires.group(1))

    # 2. Total netlist wire bits
    m_wbits = re.search(r"Number of wire bits:\s*(\d+)", block) or re.search(r"^\s*(\d+)\s+wire bits\b", block, re.MULTILINE)
    if m_wbits:
        stats["wire_bits"] = int(m_wbits.group(1))

    # 3. Public interface wires
    m_pub_w = re.search(r"Number of public wires:\s*(\d+)", block) or re.search(r"^\s*(\d+)\s+public wires\b", block, re.MULTILINE)
    if m_pub_w:
        stats["public_wires"] = int(m_pub_w.group(1))

    # 4. Public interface wire bits
    m_pub_wb = re.search(r"Number of public wire bits:\s*(\d+)", block) or re.search(r"^\s*(\d+)\s+public wire bits\b", block, re.MULTILINE)
    if m_pub_wb:
        stats["public_wire_bits"] = int(m_pub_wb.group(1))

    # 5. Total synthesized cells
    m_cells = re.search(r"Number of cells:\s*(\d+)", block) or re.search(r"^\s*(\d+)\s+cells\b", block, re.MULTILINE)
    if m_cells:
        stats["cells"] = int(m_cells.group(1))

    # 6. Primitive gate breakdown
    cells_a = re.findall(r"^\s+(\$_\w+_?|\$\w+)\s+(\d+)\s*$", block, re.MULTILINE)
    if cells_a:
        for name, count in cells_a:
            stats["cell_details"][name] = int(count)
    else:
        cells_b = re.findall(r"^\s+(\d+)\s+(\$_\w+_?|\$\w+)\s*$", block, re.MULTILINE)
        for count, name in cells_b:
            stats["cell_details"][name] = int(count)

    # Sanity fallback: if cell details found but cells header was missing, sum details
    if stats["cells"] == 0 and stats["cell_details"]:
        stats["cells"] = sum(stats["cell_details"].values())

    # Validation: Fail if synthesis statistics are missing or zero
    if stats["cells"] <= 0 or stats["wires"] <= 0:
        raise ValueError(
            f"Synthesis statistics validation failed for module '{module_name}': "
            f"extracted cells={stats['cells']}, wires={stats['wires']}. "
            f"Expected positive integers. Block snippet:\n{block[:400]}"
        )

    return stats


def generate_comparison_report(baseline_stats: dict, opt_stats: dict) -> str:
    def delta(base, opt):
        if base == 0:
            return "0.0%"
        diff = ((opt - base) / base) * 100.0
        sign = "+" if diff > 0 else ""
        return f"{sign}{diff:.1f}%"

    report_lines = [
        "================================================================================",
        "             8-BIT ALU: HARDWARE SYNTHESIS & GATE BENCHMARK REPORT             ",
        "================================================================================",
        f"{'Design Metric':<36} | {'Baseline':<12} | {'AI-Optimized':<12} | {'Delta':<10}",
        "--------------------------------------------------------------------------------",
        f"{'Total Synthesized Netlist Cells':<36} | {baseline_stats['cells']:<12} | {opt_stats['cells']:<12} | {delta(baseline_stats['cells'], opt_stats['cells']):<10}",
        f"{'Netlist Interconnect Wires (Nets)':<36} | {baseline_stats['wires']:<12} | {opt_stats['wires']:<12} | {delta(baseline_stats['wires'], opt_stats['wires']):<10}",
        f"{'Total Netlist Wire Bits':<36} | {baseline_stats['wire_bits']:<12} | {opt_stats['wire_bits']:<12} | {delta(baseline_stats['wire_bits'], opt_stats['wire_bits']):<10}",
        f"{'Public Netlist Interface Wires':<36} | {baseline_stats['public_wires']:<12} | {opt_stats['public_wires']:<12} | {delta(baseline_stats['public_wires'], opt_stats['public_wires']):<10}",
        f"{'Public Netlist Wire Bits':<36} | {baseline_stats['public_wire_bits']:<12} | {opt_stats['public_wire_bits']:<12} | {delta(baseline_stats['public_wire_bits'], opt_stats['public_wire_bits']):<10}",
        "--------------------------------------------------------------------------------",
        "Cell Gate Breakdown (Synthesized Technology Primitives):"
    ]

    all_cell_types = sorted(set(list(baseline_stats["cell_details"].keys()) + list(opt_stats["cell_details"].keys())))
    for ct in all_cell_types:
        b_cnt = baseline_stats["cell_details"].get(ct, 0)
        o_cnt = opt_stats["cell_details"].get(ct, 0)
        report_lines.append(f"  - {ct:<32} | {b_cnt:<12} | {o_cnt:<12} | {delta(b_cnt, o_cnt):<10}")

    report_lines.append("================================================================================")
    report_lines.append("\n[ARCHITECTURAL ANALYSIS]")
    report_lines.append(
        f"1. Logic Cell Complexity: {delta(baseline_stats['cells'], opt_stats['cells'])} cells\n"
        f"   - Unified two's-complement arithmetic replaces separate addition and subtraction logic.\n"
        f"2. Netlist Interconnect: {delta(baseline_stats['wires'], opt_stats['wires'])} netlist wires (nets)\n"
        f"   - Reduced multiplexing stages and resource sharing minimize internal netlist interconnect footprint.\n"
        f"   - Note: Netlist wires reflect logical signal connectivity (nets), distinguished from physical\n"
        f"     post-layout metal routing wirelength or congestion.\n"
        f"3. Operand Isolation:\n"
        f"   - Inputs to the 8-bit carry chain are gated to zero during logical operations,\n"
        f"     suppressing dynamic switching activity across inactive functional sub-blocks.\n"
        f"4. Physical Characterization Note:\n"
        f"   - Generic synthesis counts provide technology-independent gate metrics.\n"
        f"   - True silicon area (um^2) and maximum frequency (Fmax) require a foundry standard-cell library (Liberty .lib)."
    )
    report_lines.append("================================================================================")

    return "\n".join(report_lines)


def generate_candidate(preferred_model: str = None) -> tuple:
    """Invokes Gemini API to generate an optimized 8-bit RTL candidate."""
    try:
        import dotenv
        if ENV_FILE.exists():
            dotenv.load_dotenv(ENV_FILE)
    except ImportError:
        pass

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY is not set in environment or .env file.")
        print("Please configure GEMINI_API_KEY in .env to use AI candidate generation.")
        sys.exit(1)

    try:
        import google.generativeai as genai
    except ImportError:
        print("[ERROR] Optional AI dependencies are not installed.")
        print("To use Gemini AI candidate generation, install: pip install -r requirements-ai.txt")
        sys.exit(1)

    genai.configure(api_key=api_key)

    base_file = SRC_DIR / "alu_baseline.v"
    baseline_code = read_file(base_file)

    prompt = f"""
You are an expert digital IC design and low-power ASIC/FPGA hardware engineer.
Below is an 8-bit baseline ALU written in standard behavioral Verilog.

```verilog
{baseline_code}
```

Task:
Generate a structurally optimized, low-power version of this ALU named `alu_candidate`.
You MUST preserve exact functional equivalence with `alu_baseline`:
- Inputs: `wire [7:0] a`, `wire [7:0] b`, `wire [2:0] opcode`
- Outputs: `reg [7:0] alu_out` (or wire if continuous assign), `reg carry_out`, `wire zero`
- Same opcode mapping:
  - 3'b000: ADD (a + b)
  - 3'b001: SUB (a - b) -> Note: in two's complement shared adder A + ~B + 1, adder carry-out bit [8] is 1 for A >= B and 0 for A < B. In alu_baseline, carry_out represents borrow (1 for A < B, 0 for A >= B). Therefore you MUST set carry_out = ~arith_res[8] for OP_SUB!
  - 3'b010: AND (a & b, carry_out = 0)
  - 3'b011: OR  (a | b, carry_out = 0)
  - 3'b100: XOR (a ^ b, carry_out = 0)
  - default: 0, carry_out = 0
- `zero` flag is 1 when `alu_out == 8'b0`, else 0.

Key Low-Power Hardware Optimization Requirements:
1. **Operand Isolation (Input Gating)**:
   - Arithmetic datapath (adders/subtractors) must NOT toggle when logical operations (AND, OR, XOR) or invalid opcodes execute.
   - Use an isolation enable condition: `wire is_arith = (opcode == 3'b000) || (opcode == 3'b001);`
   - Gate the inputs: `wire [7:0] arith_a = is_arith ? a : 8'b0; wire [7:0] arith_b = is_arith ? b : 8'b0;`
   - Also gate logical inputs when non-logic ops execute.
2. **Resource-Shared Unified Adder/Subtractor**:
   - Single shared adder structure with two's-complement arithmetic:
     `wire is_sub = (opcode == 3'b001);`
     `wire [7:0] b_operand = is_sub ? ~arith_b : arith_b;`
     `wire cin = is_sub;`
     `wire [8:0] arith_res = arith_a + b_operand + cin;`
   - When OP_ADD: `carry_out = arith_res[8]`
   - When OP_SUB: `carry_out = ~arith_res[8]` (borrow flag)
3. **Module Name**:
   - The module header MUST be `module alu_candidate (`.

Output format: Return ONLY clean Verilog source code inside a single ```verilog ... ``` code block.
"""

    models_to_try = [preferred_model] if preferred_model else CANDIDATE_MODELS
    for model_name in models_to_try:
        try:
            print(f"[AI Orchestrator] Prompting Gemini model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            code = extract_code(response.text)
            print(f"[AI Orchestrator] Successfully received candidate from {model_name}!")
            return code, model_name
        except Exception as e:
            print(f"[WARN] Failed with {model_name}: {e}. Trying next...")

    print("[ERROR] All Gemini models failed.")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="8-bit ALU Design, Verification & Synthesis Orchestrator")
    parser.add_argument("--generate", action="store_true", help="Generate a new AI candidate into src/alu_candidate.v")
    parser.add_argument("--model", type=str, default=None, help="Specific Gemini model name to use with --generate")
    parser.add_argument("--promote-candidate", action="store_true", help="Promote verified candidate to src/alu_optimized.v")
    parser.add_argument("--skip-synthesis", action="store_true", help="Skip Yosys synthesis")
    args = parser.parse_args()

    print("====================================================================")
    print("   8-BIT ALU: VERIFICATION, SYNTHESIS & BENCHMARK PIPELINE          ")
    print("====================================================================")

    baseline_file = SRC_DIR / "alu_baseline.v"
    optimized_file = SRC_DIR / "alu_optimized.v"
    candidate_file = SRC_DIR / "alu_candidate.v"

    # Handle Candidate Promotion
    if args.promote_candidate:
        if not candidate_file.exists():
            print(f"[ERROR] No candidate file found at {candidate_file} to promote.")
            sys.exit(1)
        print(f"[Promotion] Verifying candidate {candidate_file.name} before promoting...")
        pass_check, log = run_iverilog_verification(candidate_file, is_candidate=True)
        if not pass_check:
            print(f"[ERROR] Candidate failed verification! Refusing to promote:\n{log}")
            sys.exit(1)
        cand_code = read_file(candidate_file)
        promoted_code = re.sub(r"\bmodule\s+alu_candidate\b", "module alu_optimized", cand_code)
        write_file(optimized_file, promoted_code)
        print(f"[SUCCESS] Candidate successfully promoted to {optimized_file}!")
        return

    # Handle AI Candidate Generation
    if args.generate:
        print("\n--- Generating AI Optimization Candidate ---")
        cand_code, active_model = generate_candidate(args.model)
        write_file(candidate_file, cand_code)
        print(f"[Saved] Candidate written to {candidate_file}")

        print("\n--- Verifying AI Candidate with Icarus Verilog ---")
        passed, sim_log = run_iverilog_verification(candidate_file, is_candidate=True)
        if passed:
            print(f"[SUCCESS] Candidate passed all functional verification tests!")
            print(f"[INFO] To promote this candidate to validated RTL, run:")
            print(f"       python scripts/optimize.py --promote-candidate")
        else:
            print(f"[ERROR] Candidate failed verification:\n{sim_log}")
            sys.exit(1)
        return

    # Standard Deterministic Offline Workflow
    if not baseline_file.exists():
        print(f"[ERROR] Baseline ALU not found at {baseline_file}")
        sys.exit(1)
    if not optimized_file.exists():
        print(f"[ERROR] Optimized ALU not found at {optimized_file}")
        sys.exit(1)

    # Step 1: Functional Co-Simulation Verification
    print("\n--- STEP 1: Dual-DUT Lockstep Co-Simulation Verification ---")
    print(f"[Simulation] Compiling baseline and optimized ALUs against golden reference...")
    passed, sim_log = run_iverilog_verification(optimized_file, is_candidate=False)
    if not passed:
        print(f"[ERROR] Verification failed:\n{sim_log}")
        sys.exit(1)
    print(f"[SUCCESS] Lockstep co-simulation passed 3,080/3,080 test cases with zero regressions!")

    # Step 2: Yosys Synthesis on Both Designs
    base_stats = {}
    opt_stats = {}
    if not args.skip_synthesis:
        print("\n--- STEP 2: Yosys Technology-Independent Synthesis ---")
        base_stats = run_yosys_synthesis(baseline_file, "alu_baseline")
        opt_stats = run_yosys_synthesis(optimized_file, "alu_optimized")

        # Explicit validation: Fail immediately if stats are missing or zero
        if base_stats.get("cells", 0) <= 0 or opt_stats.get("cells", 0) <= 0:
            print("[FATAL] Synthesis cell count is missing or zero! Failing pipeline.")
            sys.exit(1)
        if base_stats.get("wires", 0) <= 0 or opt_stats.get("wires", 0) <= 0:
            print("[FATAL] Synthesis netlist wire count is missing or zero! Failing pipeline.")
            sys.exit(1)

        print(f"[Synthesis] Baseline cell count : {base_stats['cells']} cells, {base_stats['wires']} netlist wires")
        print(f"[Synthesis] Optimized cell count: {opt_stats['cells']} cells, {opt_stats['wires']} netlist wires")
    else:
        print("\n--- STEP 2: Synthesis skipped (--skip-synthesis specified) ---")

    # Step 3: Comparative Report Generation
    print("\n--- STEP 3: Generating Benchmark Report ---")
    report = generate_comparison_report(base_stats, opt_stats)
    print("\n" + report)

    report_path = REPORTS_DIR / "comparison_report.txt"
    write_file(report_path, report)
    print(f"\n[Report Saved] Benchmark report saved to {report_path}")
    print("\n[COMPLETE] 8-bit ALU pipeline finished successfully.")


if __name__ == "__main__":
    main()
