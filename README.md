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

## Verification Architecture: Dual-DUT Lockstep Co-Simulation & Formal Equivalence

Both the 32-bit RISC-V ALU and the 8-bit ALU are verified using a rigorous, dual-layer verification methodology:
1. **SAT-Based Formal Equivalence Checking (Yosys)**: Mathematically proves 100% equivalence across all boolean states and control words via SAT solver (`equiv_make`, `equiv_simple`, `equiv_status -assert`).
2. **Dual-DUT Lockstep Simulation**: Simultaneously evaluates baseline RTL, optimized RTL, and an independent golden behavioral reference model across 9,136 total test vectors.

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
                                   |
                                   v
                    +-----------------------------+
                    | SAT Formal Equivalence      |
                    | Yosys Mathematical Proof    |
                    | 100% Equivalence Proven     |
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
  - **Deterministic Switching Workload Trace**: Dedicated 100-cycle deterministic workload trace dumped directly to VCD for switching activity profiling, with initialization settled prior to measurement.
  - **Fail-Safe Exit**: Uses `$fatal(1)` to guarantee a non-zero exit code on any functional divergence.

- **8-Bit ALU (`tb/alu_tb.v`) - 3,080 Total Tests**:
  - Directed corner combinations across all opcodes with unknown bit checking.
  - Dedicated carry/borrow flag checks for addition and subtraction.
  - 3,000 randomized vectors uniformly exercising all valid opcodes with lockstep equivalence against golden reference model.
  - Dedicated 100-cycle switching workload trace dumped to VCD.

---

## Power & Synthesis Benchmark Results

### 1. Dynamic Switching-Activity Profiling (VCD Waveform Toggle Profiling)
Switching activity is quantified by counting bit transitions under identical stimulus across **equivalent logical datapath boundaries** using an exact hierarchical VCD parser (`scripts/vcd_parser.py`). Initialization transitions are settled prior to the measurement window.

#### 32-Bit RISC-V ALU (100 Cycles):
| Datapath / Signal Boundary | RV32I Baseline | AI-Optimized | Abs Delta | Pct Delta | Measured Cycles | Notes |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Primary ALU Inputs (A, B, Ctrl)** | 3,036 | 3,036 | 0 | **0.0%** | 100 | Identical workload applied to both DUTs |
| **Arithmetic Datapath Inputs** | 2,839 | 1,296 | -1,543 | **-54.4%** | 100 | Gated during logic & shift cycles |
| **Barrel Shifter Inputs** | 1,488 | 713 | -775 | **-52.1%** | 100 | Gated during arithmetic & logic cycles |
| **Logic Datapath Inputs** | 2,839 | 2,324 | -515 | **-18.1%** | 100 | Gated during arithmetic & shift cycles |
| **ALU Outputs (alu_out, zero)** | 1,527 | 1,527 | 0 | **0.0%** | 100 | Proves 100% output equivalence |
| *Operator Level (ADD+SUB+SLT)* | 8,517 | 1,296 | -7,221 | **-84.8%** | 100 | Unshared baseline operators vs shared 33-bit adder |

```
Visual Comparison of Dynamic Switching-Activity (32-Bit RV32I ALU):
  Primary ALU Inputs   : Base [█████████                ] 3036
                         Opt  [█████████                ] 3036 ( 0.0%)
  Arithmetic Datapath  : Base [████████                 ] 2839
                         Opt  [████                     ] 1296 (-54.4%)
  Barrel Shifter       : Base [████                     ] 1488
                         Opt  [██                       ]  713 (-52.1%)
  Logic Datapath       : Base [████████                 ] 2839
                         Opt  [███████                  ] 2324 (-18.1%)
```

#### 8-Bit ALU (100 Cycles):
| Datapath / Signal Boundary | Baseline | AI-Optimized | Abs Delta | Pct Delta | Measured Cycles | Notes |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Primary ALU Inputs (A, B, Op)** | 945 | 945 | 0 | **0.0%** | 100 | Identical stimulus applied to both DUTs |
| **Arithmetic Datapath Inputs** | 787 | 460 | -327 | **-41.6%** | 100 | Gated during logical cycles |
| **Logic Datapath Inputs** | 787 | 605 | -182 | **-23.1%** | 100 | Gated during arithmetic cycles |
| **ALU Outputs (out, carry, zero)**| 462 | 462 | 0 | **0.0%** | 100 | Proves 100% output equivalence |
| *Operator Level (ADD + SUB)* | 1,574 | 460 | -1,114 | **-70.8%** | 100 | Separate adder/subtractor vs unified shared unit |

> **Honest Physical Characterization Disclaimer**:
> Switching-activity transition counts represent simulated dynamic toggle suppression, not physical power in milliwatts ($\text{mW}$). Real physical power ($P_{\text{total}} = P_{\text{dyn}} + P_{\text{leak}}$) requires a calibrated foundry standard-cell library (`.lib`), operating voltage ($V_{dd}$), clock frequency ($f$), and post-route parasitic extraction (`SPEF`).

---

### 2. Generic Technology-Independent Netlist Complexity (Yosys `synth -noabc`)
Synthesis performed with open-source Yosys using generic CMOS technology primitive gate mapping:

#### 32-Bit RISC-V ALU:
| Netlist Metric | RV32I Baseline | AI-Optimized | Delta | Classification |
| :--- | :---: | :---: | :---: | :--- |
| **Total Synthesized Cells** | 1,485 | 1,499 | **+0.9%** | Gate Complexity |
| **Combinational Cells** | 1,485 | 1,499 | **+0.9%** | Logic Gates |
| **Sequential Cells (Registers)** | 0 | 0 | **0.0%** | Pure Combinational |
| **Netlist Interconnect Wires (Nets)** | 602 | 491 | **-18.4%** | Netlist Routing Footprint |
| **Total Netlist Wire Bits** | 1,735 | 1,712 | **-1.3%** | Bit Width Footprint |
| **`$_AND_` Gates** | 479 | 343 | **-28.4%** | Primitive |
| **`$_OR_` Gates** | 425 | 281 | **-33.9%** | Primitive |
| **`$_XOR_` Gates** | 128 | 97 | **-24.2%** | Primitive |
| **`$_MUX_` Gates** | 404 | 730 | **+80.7%** | Primitive |
| **`$_NOT_` Gates** | 49 | 48 | **-2.0%** | Primitive |

#### 8-Bit ALU:
| Netlist Metric | Baseline | AI-Optimized | Delta | Classification |
| :--- | :---: | :---: | :---: | :--- |
| **Total Synthesized Cells** | 231 | 224 | **-3.0%** | Gate Complexity |
| **Combinational Cells** | 231 | 224 | **-3.0%** | Logic Gates |
| **Sequential Cells (Registers)** | 0 | 0 | **0.0%** | Pure Combinational |
| **Netlist Interconnect Wires (Nets)** | 145 | 117 | **-19.3%** | Netlist Routing Footprint |
| **Total Netlist Wire Bits** | 260 | 248 | **-4.6%** | Bit Width Footprint |
| **`$_AND_` Gates** | 88 | 66 | **-25.0%** | Primitive |
| **`$_OR_` Gates** | 85 | 67 | **-21.2%** | Primitive |
| **`$_XOR_` Gates** | 30 | 24 | **-20.0%** | Primitive |
| **`$_MUX_` Gates** | 9 | 49 | **+444.4%** | Primitive |
| **`$_NOT_` Gates** | 19 | 18 | **-5.3%** | Primitive |

> **Netlist Wires vs. Physical Routing**: Netlist wire counts reflect logical signal interconnects (nets) in the synthesized netlist prior to physical layout. They are distinct from physical post-layout metal routing wirelength ($\mu m$) or routing track congestion, which require place-and-route (P&R).

---

## Architectural Analysis & Trade-Offs

1. **Operand Isolation (Input Gating)**:
   - Gating multiplexers freeze high-capacitance sub-blocks (32-bit carry chains and shift matrices) when idle.
   - Area-versus-Activity Trade-Off: Adding gating multiplexers introduces a small +0.9% gate count overhead in the 32-bit ALU (+80.7% muxes) in exchange for **-54.4%** dynamic toggle suppression in the adder and **-52.1%** in the shifter.
2. **Resource-Shared Arithmetic Unit**:
   - ADD, SUB, SLT, and SLTU all utilize a unified 33-bit two's-complement adder.
   - For 8-bit, this resource sharing reduces cell count by **-3.0%** and netlist wires by **-19.3%**.
3. **Timing Considerations & Limitations**:
   - Gating multiplexers introduce approximately one 2-to-1 MUX propagation delay on operand arrival.
   - Because the 32-bit ripple-carry chain and barrel shifter dominate the critical path, operand gating introduces negligible timing penalty on maximum operating frequency ($F_{\text{max}}$).
   - Technology-specific static timing analysis (STA/WNS) and physical power estimation require target foundry cell libraries (`.lib`) and physical layout (`SPEF`), which are not bundled in this offline open-source repository.

---

## Continuous Integration (GitHub Actions)

The repository includes a GitHub Actions CI workflow (`.github/workflows/ci.yml`) that:
- Runs automatically on every `push` and `pull_request` to `main`.
- Installs Icarus Verilog and pinned YowASP Yosys 0.70 on `ubuntu-latest`.
- Runs the automated **VCD parser unit test suite** (`tests/test_vcd_parser.py`).
- Compiles and runs both 8-bit and 32-bit dual-DUT testbenches in strict verification mode.
- Executes **SAT-based formal equivalence checking** via Yosys.
- Executes both pipeline orchestrator scripts and profiles dynamic switching activity.
- **Fail-Safe Assertions**: Fails the build immediately if synthesis cell counts or netlist wire counts deviate from verified baseline/optimized reference metrics.
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
- **Yosys** (pinned `yowasp-yosys` 0.70 installed via `requirements.txt`)
- **GTKWave** (optional, for waveform inspection)

### Installation
```bash
git clone https://github.com/pushkalgolla-svg/ai-low-power-riscv-alu.git
cd ai-low-power-riscv-alu
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install core offline verification dependencies (includes pinned Yosys 0.70)
pip install -r requirements.txt

# (Optional) Install AI generation dependencies if using Gemini API
pip install -r requirements-ai.txt
```

### Running the Pipelines

#### 1. Run VCD Parser Unit Tests
```bash
python -m unittest discover tests
```

#### 2. Run 32-Bit RISC-V ALU Pipeline (Simulation, Activity Profiling & Synthesis)
```bash
python scripts/optimize_riscv.py
```
Or on Windows:
```cmd
run_demo.bat
```

#### 3. Run 8-Bit ALU Pipeline
```bash
python scripts/optimize.py
```

#### 4. (Optional) Generate a New AI Optimization Candidate
```bash
# Requires GEMINI_API_KEY set in .env and requirements-ai.txt installed
python scripts/optimize_riscv.py --generate

# Promote verified candidate to production RTL
python scripts/optimize_riscv.py --promote-candidate
```

#### 5. Inspect Switching Waveforms in GTKWave
```bash
gtkwave reports/riscv_activity.vcd
```

---

## Directory Structure

```
├── .github/
│   └── workflows/
│       └── ci.yml            # Automated GitHub Actions verification & synthesis CI
├── .env.example              # Template for API keys (optional)
├── README.md                 # Project architecture, benchmarks & documentation
├── requirements.txt          # Core offline dependencies (python-dotenv, yowasp-yosys)
├── requirements-ai.txt       # Optional AI candidate generation dependencies
├── run_demo.bat              # One-click Windows runner
├── reports/
│   ├── alu_activity.vcd      # VCD trace for 8-bit switching activity profiling
│   ├── comparison_report.txt # 8-bit ALU benchmark report
│   ├── riscv_activity.vcd    # VCD trace for 32-bit switching activity profiling
│   ├── riscv_ppa_report.txt  # 32-bit RISC-V PPA benchmark report
│   └── *_synth.stat          # Raw Yosys synthesis logs
├── scripts/
│   ├── optimize.py           # 8-bit ALU pipeline orchestrator
│   ├── optimize_riscv.py     # 32-bit RISC-V ALU pipeline orchestrator
│   └── vcd_parser.py         # Exact hierarchical VCD switching-activity parser
├── src/
│   ├── alu_baseline.v        # Behavioral 8-bit baseline ALU
│   ├── alu_optimized.v       # Low-power 8-bit ALU with operand isolation
│   ├── riscv_alu_baseline.v  # Standard 32-bit RV32I ALU
│   └── riscv_alu_optimized.v # Low-power 32-bit RV32I ALU (gated datapaths)
├── tb/
│   ├── alu_tb.v              # 8-bit dual-DUT + golden model testbench (3,080 vectors)
│   └── riscv_alu_tb.v        # 32-bit dual-DUT + golden model testbench (6,056 vectors)
└── tests/
    └── test_vcd_parser.py    # Automated unit tests for VCD parser
```

---

## Resume Bullet Points

- **Low-Power ASIC Architecture & Design for RISC-V (RV32I) Core**:
  - Architected an automated low-power PPA optimization and verification pipeline in Verilog (IEEE 1364-2001) for a 32-bit RISC-V ALU across all 10 standard integer computational instructions.
  - Implemented multi-datapath Operand Isolation and unified two's-complement arithmetic resource sharing, achieving **-54.4%** dynamic toggle reduction on 32-bit adder inputs, **-52.1%** reduction on barrel shifter inputs, and **-18.4%** reduction in generic netlist interconnect wires (nets).
  - Designed dual-layer verification: SAT-based formal equivalence checking (Yosys) proving 100% mathematical equivalence across all boolean states, plus dual-DUT lockstep co-simulation testbenches with **6,056 automated vectors** against an independent golden behavioral reference model.
  - Developed an exact hierarchical VCD switching-activity parser (`vcd_parser.py`) with full automated unit test suite, profiling dynamic bit transitions across equivalent datapath boundaries under identical workloads while excluding initialization transients.
  - Built a reproducible GitHub Actions CI pipeline executing automated RTL simulation, formal verification, generic CMOS synthesis, and zero-defect netlist assertions across every commit without external API dependencies.
