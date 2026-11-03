# AI-Driven Low-Power RISC-V (RV32I) ALU Design & PPA Synthesis Pipeline

An end-to-end automated hardware-software co-design pipeline that uses **Google Gemini** to perform architectural Power-Performance-Area (PPA) optimizations on a 32-bit **RISC-V (`RV32I`) ALU**, verifies functional equivalence using **Icarus Verilog**, profiles dynamic switching activity via **VCD waveform parsing**, and synthesizes physical gate-level metrics with **Yosys**.

---

## Architecture & Workflow

```
+---------------------------+        +--------------------------+
|  src/riscv_alu_baseline.v |        |      tb/riscv_alu_tb.v   |
+-------------+-------------+        +------------+-------------+
              |                                   |
              +-----------------+-----------------+
                                |
                                v
               [ Step 1: Icarus Verilog + VCD Dump ]
                                |
                                v
               [ Step 2: Google Gemini AI Optimizer ]
                                |
                                v
+-------------------------------+-------------------------------+
|                 src/riscv_alu_optimized.v                     |
|  - Operand Isolation (Gated Adders & Barrel Shifters)        |
|  - Unified 32-bit Two's-Complement Arithmetic Unit           |
+-------------------------------+-------------------------------+
                                |
                                v
               [ Step 3: Verification (22/22 Pass) ]
                                |
                                v
               [ Step 4: Yosys Technology Synthesis ]
                                |
                                v
               [ Step 5: VCD Toggle & PPA Benchmark ]
```

---

## Key Hardware Optimizations

1. **Multi-Datapath Operand Isolation (Input Gating)**:
   - In 32-bit processors, the 32-bit carry chain and 32-bit barrel shifter represent the largest internal dynamic capacitance.
   - During logical operations (`AND`, `OR`, `XOR`), the optimized ALU gates inputs to the adder and shifter to zero, freezing all internal nodes and eliminating parasitic dynamic power ($P_{\text{dyn}} = \alpha C V^2 f$).

2. **Resource-Shared Arithmetic Unit**:
   - Merges `ADD`, `SUB`, `SLT` (signed comparison), and `SLTU` (unsigned comparison) into a single 32-bit two's-complement arithmetic structure.

---

## PPA Benchmark Results

```
========================================================================================
          32-BIT RISC-V (RV32I) ALU: AI-POWERED PPA BENCHMARK & FOOTPRINT REPORT        
========================================================================================
Design Metric                        | RV32I Baseline  | AI-Optimized    | Delta     
----------------------------------------------------------------------------------------
32-bit Adder Input Transitions       | 1816            | 316             | -82.6%    
32-bit Shifter Input Transitions     | 1816            | 206             | -88.7%    
Total Synthesized Logic Cells        | 1485            | 1434            | -3.4%     
Estimated Silicon Area (um^2)        | 12622.5         | 12189.0         | -3.4%     
Interconnect Routing Wires           | 602             | 489             | -18.8%    
Total Wire Bits                      | 1735            | 1649            | -5.0%     
----------------------------------------------------------------------------------------
Synthesized CMOS Technology Primitive Gate Counts:
  - $_AND_                           | 479             | 342             | -28.6%    
  - $_MUX_                           | 404             | 666             | +64.9%    
  - $_NOT_                           | 49              | 48              | -2.0%     
  - $_OR_                            | 425             | 281             | -33.9%    
  - $_XOR_                           | 128             | 97              | -24.2%    
========================================================================================
```

---

## Quick Start / How to Run

### 1. Prerequisites
- **Python 3.11+**
- **Icarus Verilog (`iverilog` & `vvp`)**
- **Yosys** (e.g. `yowasp-yosys`)
- **GTKWave** (for waveform viewing)

### 2. Run the 32-bit RISC-V Pipeline
```powershell
cd low_power_alu
.venv\Scripts\python.exe scripts/optimize_riscv.py
```

To run offline using the existing optimized HDL:
```powershell
.venv\Scripts\python.exe scripts/optimize_riscv.py --use-existing
```

### 3. Run the 8-bit Baseline Pipeline
```powershell
.venv\Scripts\python.exe scripts/optimize.py
```

### 4. View Switching Activity Waveforms in GTKWave
```powershell
gtkwave reports/riscv_baseline_activity.vcd
gtkwave reports/riscv_optimized_activity.vcd
```
