"""
VCD (Value Change Dump) Switching-Activity Parser
-------------------------------------------------
Features:
1. Exact hierarchical scope and signal path resolution (no ambiguous suffix matching).
2. Clean separation of initialization dump ($dumpvars) from active simulation transitions.
3. IEEE 1364 compliant vector width normalization and sign/zero extension.
4. Robust handling of unknown (X/Z) values: tracks valid rail-to-rail (0 <-> 1) transitions
   representing physical dynamic switching activity while ignoring indeterminate states.
5. Optional measurement time-window filtering [start_time, end_time].
6. Protection against signal aliasing and double-counting.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set


class VCDParser:
    def __init__(self, vcd_path: Optional[Path] = None, start_time: Optional[int] = None, end_time: Optional[int] = None):
        self.vcd_path = Path(vcd_path) if vcd_path else None
        self.start_time = start_time
        self.end_time = end_time

        # Hierarchy & metadata
        self.id_to_signals: Dict[str, List[Tuple[str, int]]] = {}  # id -> list of (full_path, bit_width)
        self.signal_to_width: Dict[str, int] = {}                  # full_path -> bit_width
        self.signal_values: Dict[str, str] = {}                    # full_path -> current normalized string
        self.signal_toggles: Dict[str, int] = {}                   # full_path -> cumulative bit transitions
        self.all_scopes: Set[str] = set()

        if self.vcd_path and self.vcd_path.exists():
            self.parse()

    @staticmethod
    def normalize_vector(val: str, width: int) -> str:
        """
        Normalizes a raw VCD vector value string to its declared width according
        to IEEE 1364-2001 standard extension rules.
        """
        val = val.strip().lower()
        if not val:
            return "0" * width

        if len(val) == width:
            return val
        elif len(val) < width:
            leading = val[0]
            pad_char = "x" if leading == "x" else ("z" if leading == "z" else "0")
            return val.rjust(width, pad_char)
        else:
            # Truncate to declared width from right
            return val[-width:]

    @staticmethod
    def count_bit_transitions(prev: str, curr: str) -> int:
        """
        Counts valid rail-to-rail (0 <-> 1) bit transitions between two normalized
        value strings of equal width. Transitions to/from X or Z are excluded from
        switching activity as they do not represent physical dynamic power toggles.
        """
        if len(prev) != len(curr):
            max_len = max(len(prev), len(curr))
            prev = prev.rjust(max_len, "0")
            curr = curr.rjust(max_len, "0")

        toggles = 0
        for p, c in zip(prev, curr):
            if p != c and p in ("0", "1") and c in ("0", "1"):
                toggles += 1
        return toggles

    def parse(self, vcd_text: Optional[str] = None):
        """Parses the VCD file or raw text string."""
        if vcd_text is not None:
            lines = vcd_text.splitlines()
        elif self.vcd_path:
            with open(self.vcd_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        else:
            raise ValueError("No VCD file path or text content provided.")

        scope_stack: List[str] = []
        in_header = True
        in_dumpvars = False
        current_time = 0

        # Step 1: Parse Header Definitions
        for line in lines:
            line = line.strip()
            if not line:
                continue

            if in_header:
                if line.startswith("$scope"):
                    parts = line.split()
                    if len(parts) >= 3:
                        scope_name = parts[2]
                        scope_stack.append(scope_name)
                        self.all_scopes.add(".".join(scope_stack))
                elif line.startswith("$upscope"):
                    if scope_stack:
                        scope_stack.pop()
                elif line.startswith("$var"):
                    parts = line.split()
                    if len(parts) >= 5:
                        var_type = parts[1]
                        try:
                            var_size = int(parts[2])
                        except ValueError:
                            var_size = 1
                        var_id = parts[3]
                        raw_name = parts[4]
                        # Strip bit range if appended e.g. a[31:0] -> a
                        clean_name = re.sub(r"\[.*?\]", "", raw_name)
                        full_path = ".".join(scope_stack + [clean_name])

                        if var_id not in self.id_to_signals:
                            self.id_to_signals[var_id] = []
                        self.id_to_signals[var_id].append((full_path, var_size))
                        self.signal_to_width[full_path] = var_size
                        self.signal_toggles[full_path] = 0
                elif line.startswith("$enddefinitions"):
                    in_header = False
                continue

            # Step 2: Parse Simulation Value Changes
            if line.startswith("$dumpvars"):
                in_dumpvars = True
                continue
            elif in_dumpvars and line.startswith("$end"):
                in_dumpvars = False
                continue

            # Timestamp parsing
            if line.startswith("#"):
                try:
                    current_time = int(line[1:])
                except ValueError:
                    pass
                continue

            # Determine whether current timestamp falls within the measurement window
            in_window = True
            if self.start_time is not None and current_time < self.start_time:
                in_window = False
            if self.end_time is not None and current_time > self.end_time:
                in_window = False

            # Vector changes: b<binary> <var_id>
            if line.startswith("b") or line.startswith("B"):
                parts = line.split()
                if len(parts) >= 2:
                    raw_val = parts[0][1:]
                    var_id = parts[1]
                    if var_id in self.id_to_signals:
                        for full_path, width in self.id_to_signals[var_id]:
                            norm_val = self.normalize_vector(raw_val, width)
                            prev_val = self.signal_values.get(full_path)

                            # Record value without counting toggle during initial dumpvars
                            if in_dumpvars or prev_val is None:
                                self.signal_values[full_path] = norm_val
                            else:
                                if in_window:
                                    diff = self.count_bit_transitions(prev_val, norm_val)
                                    self.signal_toggles[full_path] += diff
                                self.signal_values[full_path] = norm_val

            # Scalar changes: <val><var_id> (e.g., 0!, 1!, x!, z!)
            elif line[0] in ("0", "1", "x", "X", "z", "Z") and len(line) >= 2 and not line.startswith("$"):
                val = line[0].lower()
                var_id = line[1:]
                if var_id in self.id_to_signals:
                    for full_path, width in self.id_to_signals[var_id]:
                        prev_val = self.signal_values.get(full_path)
                        if in_dumpvars or prev_val is None:
                            self.signal_values[full_path] = val
                        else:
                            if in_window:
                                if prev_val != val and prev_val in ("0", "1") and val in ("0", "1"):
                                    self.signal_toggles[full_path] += 1
                            self.signal_values[full_path] = val

    def get_transitions(self, exact_hierarchical_path: str) -> int:
        """
        Returns the exact transition count for a signal path.
        Returns 0 if the signal is not present in the VCD.
        """
        return self.signal_toggles.get(exact_hierarchical_path, 0)

    def get_all_transitions(self) -> Dict[str, int]:
        """Returns a dictionary of all signal paths and their transition counts."""
        return dict(self.signal_toggles)

    def has_signal(self, exact_hierarchical_path: str) -> bool:
        """Checks if an exact signal path was declared in the VCD definitions."""
        return exact_hierarchical_path in self.signal_to_width


def parse_vcd_transitions(vcd_path: Path, start_time: Optional[int] = None, end_time: Optional[int] = None) -> VCDParser:
    """Helper factory function to parse a VCD file and return a configured VCDParser."""
    return VCDParser(vcd_path=vcd_path, start_time=start_time, end_time=end_time)
