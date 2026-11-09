# AI-Driven Low-Power RISC-V (RV32I) ALU Design, Verification & Synthesis Pipeline

[![RTL Verification & Low-Power PPA CI](https://github.com/pushkalgolla-svg/ai-low-power-riscv-alu/actions/workflows/ci.yml/badge.svg)](https://github.com/pushkalgolla-svg/ai-low-power-riscv-alu/actions/workflows/ci.yml)

An end-to-end automated hardware-software co-design and verification pipeline for a 32-bit **RISC-V (`RV32I`) ALU** and an **8-bit ALU** in Verilog (IEEE 1364-2001). The pipeline implements architectural Power-Performance-Area (PPA) optimizations—principally **Multi-Datapath Operand Isolation** and **Resource-Shared Arithmetic**—empirically validates dynamic switching-activity suppression via **VCD waveform toggle profiling**, and evaluates gate complexity using **Yosys generic CMOS synthesis**.

---

## Key Hardware Architectural Optimizations

### 1. Multi-Datapath Operand Isolation (Input Gating)
In modern high-performance microprocessors, 32-bit ripple-carry / prefix adders and multi-stage barrel shifters represent major sources of dynamic capacitive load. In conventional behavioural ALUs, inputs toggle freely through all sub-blocks regardless of the active operation:
- During logical operations (`AND`, `OR`, `XOR`), the 32-bit carry chain still computes redundant additions and draws dynamic current ($P_{\text{dyn}} = \alpha \cdot C \cdot V^2 \cdot f$).
- During arithmetic operations (`ADD`, `SUB`), the barrel shifter matrix toggles uselessly.

**Optimized Implementation:**
- Datapath-level isolation enables:
  - `is_arith = (alu_ctrl == 4'b0000) || (alu_ctrl == 4'b0001) || (alu_ctrl == 4'b0011) || (alu_ctrl == 4'b0100)`
  - `is_shift = (alu_ctrl == 4'b0010) || (alu_ctrl == 4'b0110) || (alu_ctrl == 4'b0111)`
  - `is_logic = (alu_ctrl == 4'b0101) || (alu_ctrl == 4'b1000) || (alu_ctrl == 4'b1001)`
- When an execution unit is inactive, its inputs are gated to zero (`arith_a = is_arith ? a : 32'b0`, `arith_b = is_arith ? b : 32'b0`), completely freezing internal nodes and preventing spurious switching transitions.
- Subtraction carry-in and operand complement logic are strictly guarded: `sub_op = is_arith && (alu_ctrl != ALU_ADD)`, preventing spurious inversion and carry assertion during logical and shift cycles.

### 2. Unified Resource-Shared Arithmetic Unit
Rather than instantiating separate operators for addition, subtraction, signed comparison (`SLT`), and unsigned comparison (`SLTU`), all four operations are folded into a single unified 33-bit two's-complement adder:
- `b_comp = sub_op ? ~arith_b : arith_b`
- `add_sub_res = arith_a + b_comp + sub_op`
- `SLT` (Signed Comparison): evaluates sign bits and adder sign:
  `slt_res = (arith_a[31] != arith_b[31]) ? arith_a[31] : add_sub_res[31]`
- `SLTU` (Unsigned Comparison): evaluates adder borrow/carry-out:
  `sltu_res = ~add_sub_res[32]`

---

## Verification Architecture & Testbenches

Both the 32-bit RISC-V ALU and the 8-bit ALU are verified using dual-DUT lockstep co-simulation testbenches that evaluate the baseline RTL, optimized RTL, and an independent behavioral golden reference model simultaneously.

```
                    +-----------------------------+
                    |  Test Stimulus Generator    |
                    | (Corners + Pseudo-Random)   |
                    +--------------+--------------+
                                   |
            +----------------------+----------------------+
            |                      |                      |
            v                      v                      v
   +-----------------+    +-----------------+    +-----------------+
   | Baseline DUT    |    | Optimized DUT   |    | Golden Model    |
   | (Un-isolated)   |    | (Gated Datapath)|    | (Behavioral)    |
   +--------+--------+    +--------+--------+    +--------+--------+
            |                      |                      |
            +----------------------+----------------------+
                                   |
                                   v
                    +-----------------------------+
                    | Lockstep Equivalence Check  |
                    | Baseline == Opt == Golden   |
                    | (Rejects X/Z; $fatal on err)|
                    +-----------------------------+
```

### Test Coverage Highlights:
- **32-Bit RISC-V (`tb/riscv_alu_tb.v`) - 6,056 Total Tests**:
  - **Exhaustive Corner Cross-Products (1,024 vectors)**: All combinations of $\{0, 1, -1, \text{MaxPos}, \text{MinNeg}, \text{0xAAAA\_AAAA}, \text{0x5555\_5555}, \text{0x1234\_5678}\}$ across all 16 opcode slots. Safe bit-masking (`idx & 32'd7`) prevents signed modulo issues.
  - **Shift Boundary Checks**: Shifts by $0, 1, 31, 32$ (wraps to 0), $63$ (wraps to 31), and `0xFFFFFFFF` (wraps to 31) for `SLL`, `SRL`, and arithmetic sign extension for `SRA`.
  - **Signed/Unsigned Comparison Checks**: Extreme signed values (`MinNeg < MaxPos`, `MaxPos < MinNeg`, $-1 < 0$, $0 < -1$), and unsigned wrapping.
  - **ADD / SUB Overflow**: Signed overflow wraps to `0x80000000`, unsigned overflow wraps to 0.
  - **5,000 Randomized Vectors**: Genuinely exercises all 10 supported RISC-V instructions (450 tests each) and invalid opcodes with biased random data spaces.
  - **Unknown Value Rejection**: Rejects unknown (`X`/`Z`) inputs and outputs; fails immediately if non-deterministic states appear.
  - **Dedicated Switching Workload Trace**: Isolated 100-cycle deterministic workload trace dumped directly to VCD for switching activity profiling (separated from functional verification).
  - **Fail-Safe Exit**: Uses `$fatal(1)` to guarantee a non-zero exit code on any functional divergence.

- **8-Bit ALU (`tb/alu_tb.v`) - 3,080 Total Tests**:
  - Directed corner combinations across all opcodes with unknown bit checking.
  - Dedicated carry/borrow flag checks for addition and subtraction.
  - 3,000 randomized vectors uniformly exercising all valid opcodes with lockstep equivalence against golden reference model.

---

## Power & Synthesis Benchmark Results

### 1. Dynamic Switching-Activity Profiling (32-Bit RISC-V ALU)
Switching activity is quantified by counting signal bit transitions from identical VCD traces dumped during the dedicated 100-cycle workload trace (`tb/riscv_alu_tb.v`):

| Design Metric | RV32I Baseline | AI-Optimized | Delta | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Primary ALU Inputs** | 3,050 | 3,050 | **0.0%** | Identical test workload applied to both DUTs |
| **32-bit Adder Inputs** | 2,851 | 1,328 | **-53.4%** | Toggles frozen during logic & shift cycles |
| **Barrel Shifter Inputs** | 1,494 | 713 | **-52.3%** | Toggles frozen during arithmetic & logic cycles |
| **Logic Datapath Inputs** | 2,851 | 2,352 | **-17.5%** | Toggles frozen during arithmetic & shift cycles |
| **ALU Output Transitions** | 1,555 | 1,555 | **0.0%** | Exact match proves zero functional regression |

> **Engineering Disclaimer**: Switching-activity transition counts measure dynamic toggle suppression, not absolute power in milliwatts ($\text{mW}$). Real physical power ($P_{\text{total}} = P_{\text{dyn}} + P_{\text{leak}}$) requires a calibrated foundry standard-cell library (`.lib`) and post-route parasitic extraction (`SPEF`).

### 2. Generic Technology-Independent Netlist Complexity (Yosys `synth -noabc`)
Synthesis performed with open-source Yosys using generic CMOS technology primitive gate mapping:

#### 32-Bit RISC-V ALU:
| Metric | RV32I Baseline | AI-Optimized | Delta |
| :--- | :--- | :--- | :--- |
| **Total Synthesized Netlist Cells** | 1,485 | 1,499 | **+0.9%** |
| **Netlist Interconnect Wires (Nets)** | 602 | 491 | **-18.4%** |
| **Total Netlist Wire Bits** | 1,735 | 1,712 | **-1.3%** |
| **`$_AND_` Gates** | 479 | 343 | **-28.4%** |
| **`$_OR_` Gates** | 425 | 281 | **-33.9%** |
| **`$_XOR_` Gates** | 128 | 97 | **-24.2%** |
| **`$_MUX_` Gates** | 404 | 730 | **+80.7%** |

*Analysis*: Operand isolation introduces input gating multiplexers (+80.7% muxes, +0.9% overall cells), trading a negligible gate count delta for a massive **>50% reduction in dynamic toggles** in the 32-bit execution units, while reducing generic netlist interconnect wires by **-18.4%**.

> **Netlist Wires vs. Physical Routing**: Netlist wire counts reflect logical signal interconnects (nets) in the synthesized netlist prior to physical layout. They are distinct from physical post-layout metal routing wirelength ($\mu m$) or routing track congestion, which require place-and-route (P&R).

#### 8-Bit ALU:
| Metric | Baseline | AI-Optimized | Delta |
| :--- | :--- | :--- | :--- |
| **Total Synthesized Netlist Cells** | 231 | 224 | **-3.0%** |
| **Netlist Interconnect Wires (Nets)** | 145 | 117 | **-19.3%** |
| **Total Netlist Wire Bits** | 260 | 248 | **-4.6%** |

---

## Continuous Integration (GitHub Actions)

The repository includes a GitHub Actions CI workflow (`.github/workflows/ci.yml`) that:
- Runs automatically on every `push` and `pull_request` to `main`.
- Installs Icarus Verilog and Yosys on `ubuntu-latest`.
- Compiles and runs both the 8-bit and 32-bit dual-DUT testbenches in strict verification mode.
- Executes the offline orchestrator scripts and verifies all report artifacts.
- **Fail-Safe Statistics Assertion**: Fails the build immediately if synthesis cell counts or netlist wire counts are missing, unparsed, or zero.
- Operates **100% offline** using lightweight core dependencies without requiring any API keys.

---

## AI Candidate Workflow & Safe RTL Integration

To prevent generated AI models from silently overwriting validated RTL:
1. **Offline by Default**: Standard execution does NOT require any API keys or network connection. Running `python scripts/optimize_riscv.py` evaluates validated RTL deterministically.
2. **Candidate Isolation**: When `--generate` is passed, Gemini generates an optimization candidate into `src/riscv_alu_candidate.v`.
3. **Automated Verification**: The candidate is automatically compiled and tested against the 6,056-vector testbench (`-DTEST_CANDIDATE`).
4. **Explicit Promotion**: Only when `--promote-candidate` is explicitly invoked is the verified candidate promoted to `src/riscv_alu_optimized.v`.

---

## Quickstart & Reproduction Guide

### Prerequisites
- **Python 3.10+**
- **Icarus Verilog (`iverilog` & `vvp`)**
- **Yosys** (e.g. `yowasp-yosys` or standard native Yosys)
- **GTKWave** (optional, for waveform inspection)

### Installation
```bash
git clone https://github.com/pushkalgolla-svg/ai-low-power-riscv-alu.git
cd ai-low-power-riscv-alu
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install core offline verification dependencies (minimal)
pip install -r requirements.txt

# (Optional) Install AI generation dependencies if using Gemini API
pip install -r requirements-ai.txt
```

### Running the Pipelines

#### 1. Run 32-Bit RISC-V ALU Pipeline (Simulation, Activity Profiling & Synthesis)
```bash
python scripts/optimize_riscv.py
```
Or on Windows:
```cmd
run_demo.bat
```

#### 2. Run 8-Bit ALU Pipeline
```bash
python scripts/optimize.py
```

#### 3. (Optional) Generate a New AI Optimization Candidate
```bash
# Requires GEMINI_API_KEY set in .env and requirements-ai.txt installed
python scripts/optimize_riscv.py --generate

# Promote verified candidate to production RTL
python scripts/optimize_riscv.py --promote-candidate
```

#### 4. Inspect Switching Waveforms in GTKWave
```bash
gtkwave reports/riscv_activity.vcd
```
Compare `dut_base` vs `dut_opt` execution unit activity side-by-side in real time.

---

## Directory Structure

```
├── .github/
│   └── workflows/
│       └── ci.yml            # Automated GitHub Actions verification & synthesis CI
├── .env.example              # Template for API keys (optional)
├── README.md                 # Project architecture, benchmarks & documentation
├── requirements.txt          # Core offline dependencies (python-dotenv)
├── requirements-ai.txt       # Optional AI candidate generation dependencies
├── run_demo.bat              # One-click Windows runner
├── reports/
│   ├── comparison_report.txt # 8-bit ALU synthesis report
│   ├── riscv_activity.vcd    # VCD trace for switching activity profiling
│   ├── riscv_ppa_report.txt  # 32-bit RISC-V PPA benchmark report
│   └── *_synth.stat          # Raw Yosys synthesis logs
├── scripts/
│   ├── optimize.py           # 8-bit ALU pipeline orchestrator
│   └── optimize_riscv.py     # 32-bit RISC-V ALU pipeline orchestrator
├── src/
│   ├── alu_baseline.v        # Behavioral 8-bit baseline ALU
│   ├── alu_optimized.v       # Low-power 8-bit ALU with operand isolation
│   ├── riscv_alu_baseline.v  # Standard 32-bit RV32I ALU
│   └── riscv_alu_optimized.v # Low-power 32-bit RV32I ALU (gated datapaths)
└── tb/
    ├── alu_tb.v              # 8-bit dual-DUT + golden model testbench (3,080 vectors)
    └── riscv_alu_tb.v        # 32-bit dual-DUT + golden model testbench (6,056 vectors)
```

---

## Resume Bullet Points

- **Low-Power ASIC Architecture & Design for RISC-V (RV32I) Core**:
  - Architected an automated low-power PPA optimization and verification pipeline in Verilog (IEEE 1364-2001) for a 32-bit RISC-V ALU across all 10 standard integer computational instructions.
  - Implemented multi-datapath Operand Isolation and unified two's-complement arithmetic resource sharing, achieving **-53.4%** reduction in 32-bit adder input transitions, **-52.3%** reduction in barrel shifter transitions, and **-18.4%** reduction in generic netlist interconnect wires (nets).
  - Developed dual-DUT lockstep co-simulation testbenches with 6,056 vectors (directed corners, shift wrapping, signed overflow, and 5,000 pseudo-random stress vectors with unknown bit rejection) verified against an independent golden behavioral reference model with zero functional regressions.
  - Profiled dynamic switching activity from dedicated VCD simulation waveforms under identical workloads and synthesized generic CMOS gate-level netlists with Yosys.
  - Built GitHub Actions CI pipeline executing automated RTL simulation, synthesis, and zero-defect netlist assertions across every commit without external API dependencies.
