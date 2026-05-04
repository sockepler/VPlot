"""
Waveform file parsers for CSV, VCSV, and PSF ASCII formats.
Returns unified WaveformData for plotting.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class WaveformData:
    x_data: np.ndarray
    x_label: str = "time"
    x_unit: str = "s"
    signals: dict = field(default_factory=dict)
    signal_units: dict = field(default_factory=dict)
    # display name for legend (falls back to signal key if absent)
    signal_labels: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


def get_label(data: "WaveformData", name: str) -> str:
    return data.signal_labels.get(name, name)


def infer_unit(name: str) -> str:
    n = name.strip().lower()
    if re.match(r"v\s*\(", n) or n.startswith("voltage") or n == "v":
        return "V"
    if re.match(r"i\s*\(", n) or n.startswith("current") or n == "i":
        return "A"
    if re.match(r"p\s*\(", n) or n.startswith("power"):
        return "W"
    if "freq" in n:
        return "Hz"
    if "phase" in n:
        return "deg"
    if "db" in n:
        return "dB"
    return ""


def _detect_delimiter(lines: list[str]) -> str:
    data_lines = [l for l in lines if l.strip() and not l.strip().startswith(("#", "*", ";", "!"))]
    if not data_lines:
        return ","
    try:
        dialect = csv.Sniffer().sniff("".join(data_lines[:5]), delimiters=",\t; ")
        return dialect.delimiter
    except csv.Error:
        for delim in ["\t", ",", " ", ";"]:
            if delim in data_lines[0]:
                return delim
        return ","


def _skip_comment_lines(lines: list[str]) -> int:
    count = 0
    for line in lines:
        s = line.strip()
        if not s or s.startswith(("#", "*", "!", ";")):
            count += 1
        else:
            break
    return count


def parse_csv(filepath: str) -> WaveformData:
    path = Path(filepath)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        head_lines = []
        for _ in range(50):
            line = f.readline()
            if not line:
                break
            head_lines.append(line)

    skip = _skip_comment_lines(head_lines)
    delim = _detect_delimiter(head_lines[skip:])

    comment_char = None
    for prefix in ("#", "*", "!", ";"):
        if any(l.strip().startswith(prefix) for l in head_lines[:skip]):
            comment_char = prefix
            break

    df = pd.read_csv(
        path,
        sep=delim,
        skiprows=skip,
        comment=comment_char,
        engine="python" if delim == " " else "c",
        skipinitialspace=True,
    )
    df.columns = [c.strip() for c in df.columns]

    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            except Exception:
                pass

    df = df.dropna(how="all", axis=1)
    df = df.dropna(subset=[df.columns[0]])

    x_col = df.columns[0]
    x_data = df[x_col].to_numpy(dtype=float)

    x_label = x_col.lower()
    x_unit = "s"
    if "freq" in x_label:
        x_unit = "Hz"
        x_label = "freq"
    else:
        x_label = "time"

    signals = {}
    signal_units = {}
    for col in df.columns[1:]:
        vals = df[col].to_numpy(dtype=float)
        if not np.all(np.isnan(vals)):
            signals[col] = vals
            signal_units[col] = infer_unit(col)

    return WaveformData(
        x_data=x_data,
        x_label=x_label,
        x_unit=x_unit,
        signals=signals,
        signal_units=signal_units,
        metadata={"source": str(path), "format": "CSV", "points": str(len(x_data))},
    )


def _parse_quoted_list(text: str) -> list[str]:
    """Extract items from space/comma separated string, respecting quoted strings."""
    items = re.findall(r'"([^"]*)"', text)
    if items:
        return items
    return [s.strip() for s in re.split(r"[,;]+", text) if s.strip()]


def parse_vcsv(filepath: str) -> WaveformData:
    path = Path(filepath)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()

    meta_lines = []
    data_start = 0
    for i, line in enumerate(all_lines):
        stripped = line.strip()
        if stripped.startswith(";;") or stripped.startswith(";"):
            meta_lines.append(stripped.lstrip(";").strip())
            data_start = i + 1
        else:
            break

    metadata = {"source": str(path), "format": "VCSV"}
    x_label = "time"
    x_unit = "s"
    x_label_override = None
    signals_order: list[str] = []
    labels_list: list[str] = []
    per_signal_labels: dict[str, str] = {}

    for ml in meta_lines:
        if not ml:
            continue
        kl = ml.lower()

        if ":" in ml:
            key, _, val = ml.partition(":")
            key_s = key.strip()
            val_s = val.strip()
            metadata[key_s] = val_s
            kl_key = key_s.lower()

            if kl_key in ("x axis", "xaxis", "sweep", "x_axis"):
                parts = val_s.split()
                x_label_override = parts[0].lower() if parts else "time"

            elif kl_key in ("legend", "legends", "label", "labels",
                            "display", "display names", "signal labels"):
                labels_list = _parse_quoted_list(val_s)

            elif kl_key in ("signals", "signal names", "variables"):
                signals_order = _parse_quoted_list(val_s)

        elif "=" in ml:
            sig, _, lbl = ml.partition("=")
            sig_s = sig.strip().strip('"')
            lbl_s = lbl.strip().strip('"')
            if sig_s:
                per_signal_labels[sig_s] = lbl_s

    if x_label_override:
        x_label = x_label_override

    data_text = "".join(all_lines[data_start:])
    df = pd.read_csv(io.StringIO(data_text), sep=",", skipinitialspace=True)
    df.columns = [c.strip().strip('"') for c in df.columns]

    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            except Exception:
                pass

    df = df.dropna(how="all", axis=1)

    x_col = df.columns[0]
    x_data = df[x_col].to_numpy(dtype=float)
    if "freq" in x_col.lower():
        x_unit = "Hz"
        x_label = "freq"

    signals = {}
    signal_units = {}
    signal_labels = {}

    data_signal_cols = list(df.columns[1:])

    for i, col in enumerate(data_signal_cols):
        vals = df[col].to_numpy(dtype=float)
        if not np.all(np.isnan(vals)):
            signals[col] = vals
            signal_units[col] = infer_unit(col)
            if col in per_signal_labels:
                signal_labels[col] = per_signal_labels[col]
            elif i < len(labels_list):
                signal_labels[col] = labels_list[i]

    metadata["points"] = str(len(x_data))

    return WaveformData(
        x_data=x_data,
        x_label=x_label,
        x_unit=x_unit,
        signals=signals,
        signal_units=signal_units,
        signal_labels=signal_labels,
        metadata=metadata,
    )


def is_binary_psf(filepath: str) -> bool:
    with open(filepath, "rb") as f:
        chunk = f.read(256)
    text_chars = set(range(32, 127)) | {9, 10, 13}
    non_text = sum(1 for b in chunk if b not in text_chars)
    return non_text > len(chunk) * 0.1


def parse_psf_ascii(filepath: str) -> WaveformData:
    path = Path(filepath)

    if is_binary_psf(filepath):
        raise ValueError(
            f"'{path.name}' is a binary PSF file.\n"
            "Binary PSF is not supported. Please export from Virtuoso as CSV/VCSV,\n"
            "or use 'psf2csv' / 'ocean' scripts to convert."
        )

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    lines = content.splitlines()
    state = "IDLE"
    header_info = {}
    type_defs = {}
    sweep_var = None
    sweep_type = None
    trace_names = []
    trace_types = []
    values_raw = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line or line.startswith("*"):
            i += 1
            continue

        if line.upper() == "HEADER":
            state = "HEADER"
            i += 1
            continue
        elif line.upper() == "TYPE":
            state = "TYPE"
            i += 1
            continue
        elif line.upper() == "SWEEP":
            state = "SWEEP"
            i += 1
            continue
        elif line.upper() == "TRACE":
            state = "TRACE"
            i += 1
            continue
        elif line.upper() == "VALUE":
            state = "VALUE"
            i += 1
            continue
        elif line.upper() == "END":
            state = "IDLE"
            i += 1
            continue

        if state == "HEADER":
            if '"' in line:
                parts = re.findall(r'"([^"]*)"', line)
                if len(parts) >= 2:
                    header_info[parts[0]] = parts[1]
                elif parts:
                    tokens = line.split()
                    if tokens:
                        header_info[tokens[0].strip('"')] = " ".join(parts)

        elif state == "TYPE":
            tokens = line.split()
            if len(tokens) >= 2:
                type_defs[tokens[0].strip('"')] = tokens[1].strip('"')

        elif state == "SWEEP":
            tokens = line.split()
            if tokens and not sweep_var:
                sweep_var = tokens[0].strip('"')
                if len(tokens) >= 2:
                    sweep_type = tokens[1].strip('"')

        elif state == "TRACE":
            tokens = line.split()
            if len(tokens) >= 2:
                trace_names.append(tokens[0].strip('"'))
                trace_types.append(tokens[1].strip('"'))

        elif state == "VALUE":
            values_raw.append(line)

        i += 1

    if not trace_names:
        raise ValueError(f"No TRACE signals found in PSF file '{path.name}'.")

    x_values = []
    sig_values = {name: [] for name in trace_names}

    vi = 0
    while vi < len(values_raw):
        line = values_raw[vi].strip()
        if not line:
            vi += 1
            continue

        try:
            x_val = float(line)
        except ValueError:
            vi += 1
            continue

        x_values.append(x_val)
        vi += 1

        for tname in trace_names:
            if vi < len(values_raw):
                try:
                    sig_values[tname].append(float(values_raw[vi].strip()))
                except ValueError:
                    sig_values[tname].append(np.nan)
                vi += 1

    x_data = np.array(x_values, dtype=float)
    x_label = sweep_var if sweep_var else "time"
    x_unit = "s" if "time" in x_label.lower() else ("Hz" if "freq" in x_label.lower() else "")

    signals = {}
    signal_units = {}
    for name in trace_names:
        arr = np.array(sig_values[name], dtype=float)
        if len(arr) == len(x_data):
            signals[name] = arr
            signal_units[name] = infer_unit(name)

    metadata = {
        "source": str(path),
        "format": "PSF ASCII",
        "points": str(len(x_data)),
        **header_info,
    }

    return WaveformData(
        x_data=x_data,
        x_label=x_label,
        x_unit=x_unit,
        signals=signals,
        signal_units=signal_units,
        metadata=metadata,
    )


def load_file(filepath: str) -> WaveformData:
    path = Path(filepath)
    ext = path.suffix.lower()

    if ext == ".psf":
        return parse_psf_ascii(filepath)
    elif ext == ".vcsv":
        return parse_vcsv(filepath)
    elif ext in (".csv", ".txt", ".dat", ".tsv"):
        return parse_csv(filepath)
    else:
        try:
            return parse_csv(filepath)
        except Exception:
            raise ValueError(
                f"Unsupported file format: '{ext}'\n"
                "Supported formats: .csv, .vcsv, .psf (ASCII), .txt, .dat, .tsv"
            )
