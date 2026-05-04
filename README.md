# VPlot

Analog circuit waveform viewer with IEEE-style publication-quality output.

Built for circuit designers who need to quickly inspect simulation results from Cadence Virtuoso, HSPICE, LTspice, or any tool that exports CSV/VCSV/PSF.

## Features

- **IEEE-style SI-prefix axes** — tick labels show plain numbers (0, 5, 10...); unit prefix (n, u, m...) goes into the axis label (e.g. `time [ns]`, `[mV]`). Auto-updates on zoom.
- **Multi-format input** — CSV, VCSV (Virtuoso), PSF ASCII, TSV, DAT
- **CJK support** — Chinese / Japanese signal names render correctly in legends and labels
- **Split / Merge subplots** — right-click any signal to split it into its own subplot (Virtuoso-style), or merge it back
- **Delete signals** — right-click to remove individual signals from the view (Virtuoso-style)
- **Editable labels** — double-click legend labels to rename; edit axis labels from the toolbar
- **Zoom back / forward** — navigate through your zoom history with Back/Fwd buttons
- **Cursor measurements** — click two points to see Δx, Δy, frequency
- **Publication export** — PNG (300 dpi), PDF, SVG, EPS — ready for papers
- **Style control** — font size, line width, bold, B&W line styles, grid toggle (zoom preserved on style changes)

## Install

### Linux

```bash
git clone https://github.com/YOUR_USERNAME/VPlot.git
cd VPlot
chmod +x install.sh
./install.sh
```

After install, launch with:

```bash
vp
```

> If `vp` is not found, add `~/.local/bin` to your PATH:
> ```bash
> echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
> source ~/.bashrc
> ```

**Prerequisite**: tkinter must be installed:
| Distro | Command |
|---|---|
| Ubuntu / Debian | `sudo apt install python3-tk` |
| Fedora / RHEL | `sudo dnf install python3-tkinter` |
| Arch | `sudo pacman -S tk` |

### Windows

Double-click `install.bat`, or run:

```cmd
pip install .
```

Launch with:

```cmd
vp
```

Or double-click `vp.bat` if you prefer.

### From source (no install)

```bash
pip install numpy pandas matplotlib
python -m vplot
```

## Usage

### Open a file

```bash
vp                          # launch GUI, then File > Open
vp                          # or Ctrl+O inside the app
```

### Supported formats

| Format | Extension | Source |
|---|---|---|
| CSV | `.csv` | LTspice, HSPICE, generic |
| VCSV | `.vcsv` | Cadence Virtuoso `selectResults()` |
| PSF ASCII | `.psf` | Cadence `psf2csv` export |
| Text | `.txt .dat .tsv` | Tab/space/comma delimited |

### Toolbar

| Button | Action |
|---|---|
| **Select** | Default mode — hover to see coordinates |
| **Pan** | Drag to pan the view |
| **Zoom** | Drag a rectangle to zoom in |
| **Cursor** | Click to place measurement markers (2 max) |
| **Home** | Reset to full auto-scale |
| **Back / Fwd** | Navigate zoom history |
| **PNG/PDF/SVG/EPS** | Export current view |

### Range toolbar

- **X label / Y label**: edit axis label text (press Enter to apply)
- **X range / Y range**: type values with SI suffixes (`5n`, `2.5u`, `100m`) and click Apply
- **Auto**: reset that axis to auto-scale
- **◄ ►**: switch between subplots (for Y range editing)

### Signal panel

- **Checkbox**: show/hide signals
- **Click label**: select signal for measurements
- **Double-click label**: rename the signal
- **Right-click**: split signal to own subplot, merge into another, or delete from view

### Keyboard shortcuts

| Key | Action |
|---|---|
| `Ctrl+O` | Open file |
| `Home` | Auto-scale all axes |

## VCSV format

VPlot supports an extended CSV format with metadata headers:

```
;; Title: My Simulation
;; X axis: time
;; V(out+) = Output+ Voltage
;; V(out-) = Output- Voltage
;; I(bias) = Bias Current
time, V(out+), V(out-), I(bias)
0, 0.5, 0.3, -1e-3
1e-9, 0.6, 0.4, -1e-3
...
```

## License

MIT
