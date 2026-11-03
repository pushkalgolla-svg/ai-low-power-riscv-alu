"""
AI-Powered Low-Power ALU Design & Synthesis Orchestrator
-------------------------------------------------------
1. Reads baseline Verilog ALU (src/alu_baseline.v).
2. Uses Gemini via google-generativeai to synthesize a low-power, area-optimized ALU
   employing operand isolation and resource sharing.
   - Includes automatic model fallback (gemini-flash-lite-latest, gemini-flash-latest, etc.)
   - Features automated self-repair verification loop (simulation feedback to Gemini).
   - If free-tier quota is exhausted, seamlessly falls back to validated alu_optimized.v
     or allows --use-existing flag to rerun benchmarks without consuming quota.
3. Verifies functional correctness using Icarus Verilog (iverilog & vvp).
4. Runs Yosys synthesis on both baseline and optimized designs.
5. Parses cell and wire statistics, printing a comparative benchmarking report.
"""

import os
import re
import sys
import shutil
import argparse
import warnings
import subprocess
from pathlib import Path

# Suppress deprecation and future warnings for clean output
warnings.filterwarnings("ignore")

import dotenv
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

# Setup directories
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
TB_DIR = PROJECT_ROOT / "tb"
REPORTS_DIR = PROJECT_ROOT / "reports"
ENV_FILE = PROJECT_ROOT / ".env"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Load environment & API key
if ENV_FILE.exists():
    dotenv.load_dotenv(ENV_FILE)
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    parent_env = PROJECT_ROOT.parent / "ai_verification" / ".env"
    if parent_env.exists():
        dotenv.load_dotenv(parent_env)
        api_key = os.environ.get("GEMINI_API_KEY")

if api_key:
    genai.configure(api_key=api_key)

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


def generate_optimized_alu(baseline_code: str, preferred_model: str = None) -> tuple:
    prompt = f"""
You are an expert digital IC design and low-power ASIC/FPGA hardware engineer.
Below is an 8-bit baseline ALU written in standard behavioral Verilog.

```verilog
{baseline_code}
```

Task:
Generate a structurally optimized, low-power version of this ALU named `alu_optimized`.
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
   - High-capacitance arithmetic sub-circuits (adders/subtractors) must NOT toggle when logical operations (AND, OR, XOR) or invalid opcodes are executed.
   - Use an isolation enable condition: `wire is_arith = (opcode == 3'b000) || (opcode == 3'b001);`
   - Gate the inputs to the arithmetic datapath: `wire [7:0] arith_a = is_arith ? a : 8'b0; wire [7:0] arith_b = is_arith ? b : 8'b0;`
2. **Resource-Shared Unified Adder/Subtractor**:
   - Do NOT instantiate separate `+` and `-` operators, which waste area and induce redundant switching transitions.
   - Use a single shared adder structure with two's-complement arithmetic:
     `wire is_sub = (opcode == 3'b001);`
     `wire [7:0] b_operand = is_sub ? ~arith_b : arith_b;`
     `wire cin = is_sub;`
     `wire [8:0] arith_res = arith_a + b_operand + cin;`
   - When OP_ADD: `carry_out = arith_res[8]`
   - When OP_SUB: `carry_out = ~arith_res[8]` (borrow flag)
3. **Clean, Synthesizable Verilog**:
   - Write standard IEEE 1364-2001 Verilog.
   - The module header MUST be `module alu_optimized (`.
   - Include informative comments explaining the power-saving and area-saving techniques used.

Output format: Return ONLY the clean Verilog source code inside a single ```verilog ... ``` code block without introductory or concluding conversational prose.
"""

    models_to_try = [preferred_model] if preferred_model else CANDIDATE_MODELS

    last_error = None
    for model_name in models_to_try:
        try:
            print(f"[AI Orchestrator] Prompting Gemini using model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            code = extract_code(response.text)
            print(f"[AI Orchestrator] Successfully received optimized Verilog from {model_name}!")
            return code, model_name
        except google_exceptions.ResourceExhausted as e:
            print(f"[WARN] Quota exhausted on {model_name}. Attempting next model...")
            last_error = e
        except Exception as e:
            print(f"[WARN] Error invoking {model_name}: {e}. Attempting next model...")
            last_error = e

    # Fallback to existing if available
    opt_file = SRC_DIR / "alu_optimized.v"
    if opt_file.exists():
        print("\n" + "=" * 75)
        print("[NOTICE] Gemini API daily quota limit reached on free tier.")
        print("[FALLBACK] Utilizing previously validated 'src/alu_optimized.v'")
        print("           to continue pipeline execution without error.")
        print("=" * 75 + "\n")
        return read_file(opt_file), "fallback_local"
    else:
        print(f"[ERROR] All Gemini models failed and no existing optimized file found: {last_error}")
        sys.exit(1)


def repair_optimized_alu(code: str, error_log: str, model_name: str) -> str:
    print("\n[AI Orchestrator] Running automated self-repair loop with Gemini...")
    prompt = f"""
Below is the optimized Verilog ALU implementation that failed testbench simulation:

```verilog
{code}
```

Simulation failure details:
{error_log}

Important rule for two's complement subtraction:
When implementing subtraction using A + ~B + 1:
- The adder carry-out bit [8] is 1 when A >= B (no borrow) and 0 when A < B (borrow occurred).
- The baseline ALU defines carry_out for subtraction as 1 when A < B (borrow occurred) and 0 when A >= B.
- Therefore, for OP_SUB: carry_out MUST be assigned `~arith_result[8]`!

Please fix this issue in the Verilog code and return ONLY the corrected code inside ```verilog ... ```.
"""
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        return extract_code(response.text)
    except Exception as e:
        print(f"[WARN] Self-repair API call failed ({e}). Applying direct subtraction carry correction...")
        # Direct fallback correction
        corrected = re.sub(
            r"(OP_SUB\s*:\s*begin\s+alu_out\s*=\s*arith_\w+\[7:0\];\s+carry_out\s*=\s*)(arith_\w+\[8\];)",
            r"\1~\2",
            code
        )
        if corrected == code:
            corrected = re.sub(
                r"(carry_out\s*=\s*)(arith_\w+\[8\];)",
                r"\1is_sub ? ~\2 : \2",
                code
            )
        return corrected


def run_iverilog_verification(module_path: Path, top_macro: str = None) -> tuple:
    tb_file = TB_DIR / "alu_tb.v"
    out_vvp = REPORTS_DIR / f"{module_path.stem}_sim.vvp"
    log_file = REPORTS_DIR / f"{module_path.stem}_sim.log"

    cmd = ["iverilog"]
    if top_macro:
        cmd.extend(["-D", top_macro])
    cmd.extend(["-o", str(out_vvp), str(module_path), str(tb_file)])

    comp_res = subprocess.run(cmd, capture_output=True, text=True)
    if comp_res.returncode != 0:
        return False, comp_res.stderr

    sim_res = subprocess.run(["vvp", str(out_vvp)], capture_output=True, text=True)
    write_file(log_file, sim_res.stdout)

    passed = ("ALL TESTS PASSED!" in sim_res.stdout and sim_res.returncode == 0)
    return passed, sim_res.stdout


def run_yosys_synthesis(verilog_file: Path, top_module: str) -> dict:
    print(f"\n[Synthesis] Synthesizing {verilog_file.name} (Top: {top_module}) with Yosys...")
    stat_file = REPORTS_DIR / f"{top_module}_synth.stat"

    yosys_script = f"read_verilog {verilog_file.as_posix()}; synth -noabc -top {top_module}; stat"
    yosys_cmd = shutil.which("yosys") or shutil.which("yowasp-yosys") or "yosys"

    proc = subprocess.run([yosys_cmd, "-p", yosys_script], capture_output=True, text=True)
    raw_output = proc.stdout + "\n" + proc.stderr
    write_file(stat_file, raw_output)

    if proc.returncode != 0:
        print(f"[ERROR] Yosys synthesis failed for {top_module}:\n{raw_output}")
        sys.exit(1)

    stats = parse_yosys_stats(raw_output, top_module)
    return stats


def parse_yosys_stats(output: str, module_name: str) -> dict:
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

    m_wires = re.search(r"^\s*(\d+)\s+wires\b", block, re.MULTILINE)
    if m_wires:
        stats["wires"] = int(m_wires.group(1))

    m_wbits = re.search(r"^\s*(\d+)\s+wire bits\b", block, re.MULTILINE)
    if m_wbits:
        stats["wire_bits"] = int(m_wbits.group(1))

    m_pub_w = re.search(r"^\s*(\d+)\s+public wires\b", block, re.MULTILINE)
    if m_pub_w:
        stats["public_wires"] = int(m_pub_w.group(1))

    m_pub_wb = re.search(r"^\s*(\d+)\s+public wire bits\b", block, re.MULTILINE)
    if m_pub_wb:
        stats["public_wire_bits"] = int(m_pub_wb.group(1))

    m_cells = re.search(r"^\s*(\d+)\s+cells\b", block, re.MULTILINE)
    if m_cells:
        stats["cells"] = int(m_cells.group(1))

    cell_lines = re.findall(r"^\s+(\d+)\s+(\$_\w+_?|\$\w+)\s*$", block, re.MULTILINE)
    for count, name in cell_lines:
        stats["cell_details"][name] = int(count)

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
        "             AI-POWERED LOW-POWER ALU HARDWARE SYNTHESIS BENCHMARK             ",
        "================================================================================",
        f"{'Design Metric':<30} | {'Baseline':<12} | {'AI-Optimized':<12} | {'Delta':<10}",
        "--------------------------------------------------------------------------------",
        f"{'Total Synthesized Cells':<30} | {baseline_stats['cells']:<12} | {opt_stats['cells']:<12} | {delta(baseline_stats['cells'], opt_stats['cells']):<10}",
        f"{'Total Interconnect Wires':<30} | {baseline_stats['wires']:<12} | {opt_stats['wires']:<12} | {delta(baseline_stats['wires'], opt_stats['wires']):<10}",
        f"{'Total Wire Bits':<30} | {baseline_stats['wire_bits']:<12} | {opt_stats['wire_bits']:<12} | {delta(baseline_stats['wire_bits'], opt_stats['wire_bits']):<10}",
        f"{'Public Wires':<30} | {baseline_stats['public_wires']:<12} | {opt_stats['public_wires']:<12} | {delta(baseline_stats['public_wires'], opt_stats['public_wires']):<10}",
        f"{'Public Wire Bits':<30} | {baseline_stats['public_wire_bits']:<12} | {opt_stats['public_wire_bits']:<12} | {delta(baseline_stats['public_wire_bits'], opt_stats['public_wire_bits']):<10}",
        "--------------------------------------------------------------------------------",
        "Cell Gate Breakdown (Synthesized Technology Primitives):"
    ]

    all_cell_types = sorted(set(list(baseline_stats["cell_details"].keys()) + list(opt_stats["cell_details"].keys())))
    for ct in all_cell_types:
        b_cnt = baseline_stats["cell_details"].get(ct, 0)
        o_cnt = opt_stats["cell_details"].get(ct, 0)
        report_lines.append(f"  - {ct:<26} | {b_cnt:<12} | {o_cnt:<12} | {delta(b_cnt, o_cnt):<10}")

    report_lines.append("================================================================================")

    cell_reduction = baseline_stats['cells'] - opt_stats['cells']
    wire_reduction = baseline_stats['wires'] - opt_stats['wires']

    if cell_reduction > 0:
        report_lines.append(
            f"[VERDICT] The AI-optimized ALU achieved a {delta(baseline_stats['cells'], opt_stats['cells'])} reduction in gate count\n"
            f"          and {delta(baseline_stats['wires'], opt_stats['wires'])} reduction in wiring complexity.\n"
            f"          Combined with Operand Isolation (which disables dynamic switching activity on arithmetic\n"
            f"          sub-blocks during logic operations), this provides substantial dynamic and static power savings."
        )
    elif cell_reduction == 0:
        report_lines.append(
            f"[VERDICT] The AI-optimized ALU achieved identical cell area while isolating inactive sub-blocks\n"
            f"          for reduced dynamic switching power."
        )
    else:
        report_lines.append(
            f"[VERDICT] Operand isolation introduces isolating gates for power reduction at the trade-off\n"
            f"          of modest gating logic overhead."
        )
    report_lines.append("================================================================================")

    return "\n".join(report_lines)


def main():
    parser = argparse.ArgumentParser(description="AI-Powered Low-Power ALU Design & Synthesis Orchestrator")
    parser.add_argument("--use-existing", action="store_true", help="Skip Gemini API call and use existing src/alu_optimized.v")
    parser.add_argument("--model", type=str, default=None, help="Specific Gemini model name to use")
    args = parser.parse_args()

    print("====================================================================")
    print("   AI-POWERED LOW-POWER ALU DESIGN & SYNTHESIS PIPELINE STARTING    ")
    print("====================================================================")

    baseline_file = SRC_DIR / "alu_baseline.v"
    optimized_file = SRC_DIR / "alu_optimized.v"

    if not baseline_file.exists():
        print(f"[ERROR] Baseline ALU not found at {baseline_file}")
        sys.exit(1)

    # 1. Baseline Verification
    print("\n--- STEP 1: Baseline Verification ---")
    print(f"[Verification] Compiling {baseline_file.name} with iverilog and running vvp...")
    baseline_pass, base_log = run_iverilog_verification(baseline_file)
    if not baseline_pass:
        print(f"[ERROR] Baseline ALU failed verification! Halting.\n{base_log}")
        sys.exit(1)
    print(f"[SUCCESS] {baseline_file.name} passed all functional test cases!")

    # 2. AI Optimization via Gemini
    print("\n--- STEP 2: AI Architectural Optimization ---")
    active_model = "local"
    if args.use_existing and optimized_file.exists():
        print(f"[INFO] --use-existing specified: Using existing {optimized_file}")
    else:
        baseline_code = read_file(baseline_file)
        optimized_code, active_model = generate_optimized_alu(baseline_code, preferred_model=args.model)
        write_file(optimized_file, optimized_code)
        print(f"[File Saved] AI-Optimized Verilog written to {optimized_file}")

    # 3. Optimized Verification & Self-Repair
    print("\n--- STEP 3: Optimized Design Verification ---")
    print(f"[Verification] Compiling {optimized_file.name} with iverilog and running vvp...")
    opt_pass, opt_log = run_iverilog_verification(optimized_file, top_macro="TEST_OPTIMIZED")

    if not opt_pass:
        print("[WARN] Initial simulation encountered errors. Triggering automated repair loop...")
        repaired_code = repair_optimized_alu(read_file(optimized_file), opt_log, active_model)
        write_file(optimized_file, repaired_code)
        print(f"[File Saved] Repaired Verilog written to {optimized_file}")

        print("[Verification] Re-verifying repaired ALU...")
        opt_pass, opt_log = run_iverilog_verification(optimized_file, top_macro="TEST_OPTIMIZED")

    if not opt_pass:
        print(f"[ERROR] Optimized ALU failed verification against testbench:\n{opt_log}")
        sys.exit(1)

    print(f"[SUCCESS] {optimized_file.name} passed all functional test cases!")

    # 4. Yosys Synthesis on Both Designs
    print("\n--- STEP 4: Yosys Synthesis & Benchmarking ---")
    baseline_stats = run_yosys_synthesis(baseline_file, "alu_baseline")
    opt_stats = run_yosys_synthesis(optimized_file, "alu_optimized")

    # 5. Comparative Report Generation
    print("\n--- STEP 5: Results & Footprint Comparison ---")
    report = generate_comparison_report(baseline_stats, opt_stats)
    print("\n" + report)

    report_path = REPORTS_DIR / "comparison_report.txt"
    write_file(report_path, report)
    print(f"\n[Report Saved] Full benchmark saved to {report_path}")
    print("\n[COMPLETE] AI-powered ALU design and synthesis pipeline finished successfully.")


if __name__ == "__main__":
    main()
