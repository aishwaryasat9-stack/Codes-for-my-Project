"""Interactive multi-file time-decay analyzer for Excel/CSV data.

Choose one or more workbooks. The app detects time/signal columns, fits the
selected exponential model over an adjustable elapsed-time window, and reports
lifetimes in seconds. Missing time units in headers are assumed to be seconds.
Requirements: pandas, numpy, scipy, matplotlib, openpyxl (for .xlsx/.xlsm).
"""

import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import numpy as np
    import pandas as pd
    from scipy.optimize import curve_fit
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from matplotlib.widgets import SpanSelector
except ImportError as exc:
    _DEPENDENCY_ERROR = str(exc)
else:
    _DEPENDENCY_ERROR = None

TIME_WORDS = ("time", "delay", "elapsed", "ns",
              "us", "µs", "ms", "second", "sec")
SIGNAL_WORDS = ("intensity", "signal", "count", "photon",
                "decay", "fluorescence", "emission", "response")
UNIT_TO_SECONDS = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "µs": 1e-6, "ns": 1e-9}
UNIT_LABELS = {"s": "seconds", "ms": "milliseconds",
               "us": "microseconds", "µs": "microseconds", "ns": "nanoseconds"}


def _normal(text):
    return str(text).strip().lower().replace("μ", "µ")


def _header_score(text, words):
    value = _normal(text)
    return sum(2 if word == value else 1 for word in words if word in value)


def _prepare_frame(raw, sheet_name):
    if raw is None or raw.empty:
        return None
    header_row, best_score = 0, 0
    for row in range(min(len(raw), 15)):
        cells = [str(v) for v in raw.iloc[row].tolist() if pd.notna(v)]
        score = max((_header_score(v, TIME_WORDS) for v in cells), default=0)
        score += max((_header_score(v, SIGNAL_WORDS)
                     for v in cells), default=0)
        if score > best_score:
            header_row, best_score = row, score
    labels = []
    for col in range(raw.shape[1]):
        value = raw.iat[header_row, col]
        label = str(value).strip() if pd.notna(value) else ""
        labels.append(label if label and label.lower()
                      != "nan" else f"Column {col + 1}")
    data = raw.iloc[header_row + 1:].copy().reset_index(drop=True)
    data.columns = labels
    for col in data.columns:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    numeric = [col for col in data.columns if data[col].notna().sum() >= 5]
    if len(numeric) < 2:
        return None
    return {"sheet": sheet_name, "data": data, "numeric": numeric}


def _choose_columns(candidate):
    data, cols = candidate["data"], candidate["numeric"]
    time_col = max(cols, key=lambda c: _header_score(c, TIME_WORDS))
    time_named = _header_score(time_col, TIME_WORDS) > 0
    signal_col = max((c for c in cols if c != time_col),
                     key=lambda c: _header_score(c, SIGNAL_WORDS), default=None)
    signal_named = signal_col is not None and _header_score(
        signal_col, SIGNAL_WORDS) > 0
    if not time_named:
        def time_likelihood(col):
            x = data[col].dropna().to_numpy(dtype=float)
            if len(x) < 5:
                return -1e6
            return 4 * np.mean(np.diff(x) > 0) + len(np.unique(x)) / len(x) - .03 * cols.index(col)
        time_col = max(cols, key=time_likelihood)
    if not signal_named:
        remaining = [c for c in cols if c != time_col]
        if not remaining:
            return None
        x = data[time_col].to_numpy(dtype=float)

        def decay_likelihood(col):
            y = data[col].to_numpy(dtype=float)
            good = np.isfinite(x) & np.isfinite(y)
            if good.sum() < 5:
                return -1e6
            order = np.argsort(x[good])
            yy = y[good][order]
            scale = np.nanmax(yy) - np.nanmin(yy)
            if not np.isfinite(scale) or scale == 0:
                return -1e6
            k = max(2, len(yy) // 5)
            return float((np.nanmedian(yy[:k]) - np.nanmedian(yy[-k:])) / scale) - .02 * cols.index(col)
        signal_col = max(remaining, key=decay_likelihood)
    return time_col, signal_col


def _find_trace(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        sheets = {"CSV": pd.read_csv(path, header=None)}
    elif ext in (".xlsx", ".xlsm"):
        sheets = pd.read_excel(path, sheet_name=None,
                               header=None, engine="openpyxl")
    else:
        raise ValueError("Choose .xlsx, .xlsm, or .csv files.")
    candidates = []
    for name, raw in sheets.items():
        item = _prepare_frame(raw, name)
        if item:
            selected = _choose_columns(item)
            if selected:
                item["time_col"], item["signal_col"] = selected
                paired = item["data"][item["time_col"]].notna(
                ) & item["data"][item["signal_col"]].notna()
                item["rows"] = int(paired.sum())
                item["score"] = 5 * (_header_score(item["time_col"], TIME_WORDS) + _header_score(
                    item["signal_col"], SIGNAL_WORDS)) + item["rows"] / 1000
                candidates.append(item)
    if not candidates:
        raise ValueError(
            "No sheet contained two numeric columns and at least five paired data points.")
    return max(candidates, key=lambda c: c["score"])


def _time_unit_from_header(header):
    text = _normal(header).replace("microseconds", "µs").replace(
        "microsecond", "µs").replace("usec", "us")
    matches = re.findall(
        r"(?<![a-z])(µs|us|ns|ms|sec|seconds?|s)(?![a-z])", text)
    if not matches:
        return None
    token = matches[-1]
    if token.startswith("sec") or token == "s":
        return "s"
    return token


def _single(t, amp, tau, offset):
    return amp * np.exp(-t / tau) + offset


def _bi(t, amp1, tau1, amp2, tau2, offset):
    return amp1 * np.exp(-t / tau1) + amp2 * np.exp(-t / tau2) + offset


def _stretched(t, amp, tau, beta, offset):
    return amp * np.exp(-np.power(np.maximum(t, 0) / tau, beta)) + offset


def _fit_selected(time_s, intensity, model):
    x0, y0 = np.asarray(time_s, float), np.asarray(intensity, float)
    good = np.isfinite(x0) & np.isfinite(y0)
    x0, y0 = x0[good], y0[good]
    order = np.argsort(x0)
    x0, y0 = x0[order], y0[order]
    unique = np.concatenate(([True], np.diff(x0) > 0))
    x, y = x0[unique], y0[unique]
    needed = {"Single-exponential": 4, "Bi-exponential": 7,
              "Stretched-exponential": 5}[model]
    if len(x) < needed:
        raise ValueError(
            f"Select at least {needed} distinct data points for this model.")
    t = x - x[0]
    span = float(t[-1])
    if span <= 0:
        raise ValueError("The selected time range must have a positive width.")
    baseline = float(np.median(y[-max(3, len(y)//10):]))
    amp = max(float(np.max(y) - baseline), np.finfo(float).eps)
    yrange = max(float(np.ptp(y)), np.finfo(float).eps)
    tau_min, tau_max = max(span * 1e-9, 1e-15), span * 1e3
    off_lo, off_hi = float(np.min(y) - 10*yrange), float(np.max(y) + 10*yrange)

    def fit_try(func, p0, lo, hi):
        return curve_fit(func, t, y, p0=p0, bounds=(lo, hi), maxfev=60000, x_scale="jac")

    if model == "Single-exponential":
        best = None
        for tau0 in (span/30, span/8, span/3, span, span*3):
            try:
                p, _ = fit_try(_single, [amp, max(tau0, tau_min*10), baseline],
                               [0, tau_min, off_lo], [np.inf, tau_max, off_hi])
                pred = _single(t, *p)
                sse = float(np.sum((y-pred)**2))
                if best is None or sse < best[0]:
                    best = (sse, p, pred)
            except (RuntimeError, ValueError, FloatingPointError):
                continue
        func, nparams = _single, 3
    elif model == "Bi-exponential":
        best = None
        for fast0, slow0 in ((span/40, span/3), (span/20, span/1.5), (span/10, span/2), (span/6, span*1.5), (span/30, span*2)):
            try:
                p, _ = fit_try(_bi, [amp*.6, max(fast0, tau_min*10), amp*.4, max(slow0, tau_min*20), baseline],
                               [0, tau_min, 0, tau_min, off_lo], [np.inf, tau_max, np.inf, tau_max, off_hi])
                pred = _bi(t, *p)
                sse = float(np.sum((y-pred)**2))
                if best is None or sse < best[0]:
                    best = (sse, p, pred)
            except (RuntimeError, ValueError, FloatingPointError):
                continue
        func, nparams = _bi, 5
    else:
        best = None
        for beta0 in (.5, .8, 1.0, 1.4, 1.8):
            try:
                p, _ = fit_try(_stretched, [amp, max(span/3, tau_min*10), beta0, baseline],
                               [0, tau_min, .1, off_lo], [np.inf, tau_max, 2.0, off_hi])
                pred = _stretched(t, *p)
                sse = float(np.sum((y-pred)**2))
                if best is None or sse < best[0]:
                    best = (sse, p, pred)
            except (RuntimeError, ValueError, FloatingPointError):
                continue
        func, nparams = _stretched, 4
    if best is None:
        raise ValueError(
            "Fit did not converge for this range. Try a wider window or another fit model.")
    _, params, predicted = best
    if model == "Bi-exponential" and params[1] > params[3]:
        params = np.array(
            [params[2], params[3], params[0], params[1], params[4]])
        predicted = _bi(t, *params)
    residuals = y - predicted
    sse = float(np.sum(residuals**2))
    centered = float(np.sum((y-np.mean(y))**2))
    r2 = 1-sse/centered if centered > 0 else float("nan")
    rmse = float(np.sqrt(sse/len(y)))
    aic = len(y)*np.log(max(sse/len(y), np.finfo(float).tiny))+2*nparams
    adjusted = 1-(1-r2)*(len(y)-1)/(len(y)-nparams -
                                    1) if len(y) > nparams+1 else float("nan")
    return {"time": x, "relative_time": t, "fit_start": float(x[0]), "intensity": y, "fit": predicted,
            "residual": residuals, "params": params, "metrics": {"R²": r2, "Adjusted R²": adjusted, "RMSE": rmse, "AIC": float(aic)},
            "func": func, "model": model}


class DecayApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Multi-file time-decay analyzer")
        self.geometry("1320x920")
        self.minsize(1000, 700)
        self.datasets = []
        self.results = []
        self._pending = None
        self._setting_scales = False
        self._make_ui()
        if _DEPENDENCY_ERROR:
            self.after(100, lambda: messagebox.showerror("Python packages needed",
                       "Install with:\npython -m pip install pandas numpy scipy matplotlib openpyxl\n\n"+_DEPENDENCY_ERROR))

    def _make_ui(self):
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="Add Excel/CSV files",
                   command=self.add_files).pack(side="left")
        ttk.Button(top, text="Remove selected",
                   command=self.remove_selected).pack(side="left", padx=5)
        ttk.Button(top, text="Clear all",
                   command=self.clear_files).pack(side="left")
        ttk.Button(top, text="Save combined results",
                   command=self.save_results).pack(side="left", padx=(5, 12))
        ttk.Label(top, text="Fit model").pack(side="left", padx=(0, 3))
        self.model_var = tk.StringVar(value="Single-exponential")
        self.model_box = ttk.Combobox(top, textvariable=self.model_var, state="readonly", width=21,
                                      values=("Single-exponential", "Bi-exponential", "Stretched-exponential"))
        self.model_box.pack(side="left")
        self.model_box.bind("<<ComboboxSelected>>",
                            lambda e: self._schedule_refit())
        ttk.Label(self, text="Fit window in seconds — drag across the graph or adjust the sliders. The same elapsed-time window is applied to each file.",
                  padding=(10, 2)).pack(anchor="w")
        range_box = ttk.LabelFrame(
            self, text="Interactive fit range", padding=6)
        range_box.pack(fill="x", padx=8, pady=4)
        self.start_var = tk.DoubleVar(value=0)
        self.end_var = tk.DoubleVar(value=1)
        ttk.Label(range_box, text="Start (s)").grid(
            row=0, column=0, padx=8, sticky="w")
        ttk.Label(range_box, text="End (s)").grid(
            row=0, column=1, padx=8, sticky="w")
        self.start_scale = tk.Scale(range_box, variable=self.start_var, orient="horizontal",
                                    showvalue=True, resolution=-1, length=470, command=lambda _: self._schedule_refit())
        self.end_scale = tk.Scale(range_box, variable=self.end_var, orient="horizontal",
                                  showvalue=True, resolution=-1, length=470, command=lambda _: self._schedule_refit())
        self.start_scale.grid(row=1, column=0, sticky="ew", padx=8)
        self.end_scale.grid(row=1, column=1, sticky="ew", padx=8)
        range_box.columnconfigure(0, weight=1)
        range_box.columnconfigure(1, weight=1)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=8)
        left = ttk.Frame(body, padding=5)
        right = ttk.Frame(body, padding=5)
        body.add(left, weight=1)
        body.add(right, weight=3)
        ttk.Label(left, text="Loaded files", font=(
            "Segoe UI", 11, "bold")).pack(anchor="w")
        self.file_list = tk.Listbox(
            left, height=7, selectmode="extended", exportselection=False)
        self.file_list.pack(fill="x", pady=(3, 8))
        ttk.Label(left, text="Fit results (one per file)",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.results_text = tk.Text(
            left, width=48, wrap="word", font=("Consolas", 9))
        self.results_text.pack(fill="both", expand=True)
        self.fig = Figure(figsize=(12, 7), dpi=100)
        grid = self.fig.add_gridspec(2, 2, width_ratios=(3.1, 1.7),
                                     height_ratios=(3, 1), hspace=.12, wspace=.18)
        self.ax = self.fig.add_subplot(grid[0, 0])
        self.resax = self.fig.add_subplot(grid[1, 0], sharex=self.ax)
        self.label_ax = self.fig.add_subplot(grid[:, 1])
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        NavigationToolbar2Tk(self.canvas, right,
                             pack_toolbar=False).pack(fill="x")
        self.span_selector = SpanSelector(self.ax, self._on_span, "horizontal", useblit=True, props=dict(
            alpha=.2, facecolor="tab:blue"), interactive=True)

    def _unit_for(self, item):
        return _time_unit_from_header(item["time_col"]) or "s"

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Add decay workbooks", filetypes=[(
            "Excel and CSV", "*.xlsx *.xlsm *.csv"), ("Excel workbooks", "*.xlsx *.xlsm"), ("CSV files", "*.csv")])
        if not paths:
            return
        added = []
        errors = []
        for path in paths:
            if any(d["path"] == path for d in self.datasets):
                continue
            try:
                trace = _find_trace(path)
                raw_t = trace["data"][trace["time_col"]].to_numpy(dtype=float)
                signal = trace["data"][trace["signal_col"]
                                       ].to_numpy(dtype=float)
                unit = self._unit_for(trace)
                time_s = raw_t*UNIT_TO_SECONDS[unit]
                good = np.isfinite(time_s) & np.isfinite(signal)
                if good.sum() < 5:
                    raise ValueError(
                        "Fewer than five paired numeric points were detected.")
                time_s = time_s[good]
                signal = signal[good]
                order = np.argsort(time_s)
                time_s = time_s[order]
                signal = signal[order]
                time_s = time_s-time_s[0]
                item = {"path": path, "trace": trace, "time": time_s,
                        "signal": signal, "source_unit": unit}
                self.datasets.append(item)
                added.append(item)
            except Exception as exc:
                errors.append(f"{os.path.basename(path)}: {exc}")
        self._refresh_file_list()
        self._configure_range()
        if added:
            self._schedule_refit(immediate=True)
        if errors:
            messagebox.showwarning(
                "Some files were skipped", "\n\n".join(errors))

    def _refresh_file_list(self):
        self.file_list.delete(0, "end")
        for d in self.datasets:
            self.file_list.insert("end", os.path.basename(d["path"]))

    def remove_selected(self):
        indices = list(self.file_list.curselection())
        for i in reversed(indices):
            del self.datasets[i]
        self._refresh_file_list()
        self._configure_range()
        if self.datasets:
            self._schedule_refit(immediate=True)
        else:
            self.results = []
            self.results_text.delete("1.0", "end")
            self._draw_empty()

    def clear_files(self):
        self.datasets = []
        self.results = []
        self._refresh_file_list()
        self.results_text.delete("1.0", "end")
        self._draw_empty()
        self._setting_scales = True
        self.start_scale.configure(from_=0, to=1)
        self.end_scale.configure(from_=0, to=1)
        self.start_var.set(0)
        self.end_var.set(1)
        self._setting_scales = False

    def _configure_range(self):
        if not self.datasets:
            return
        max_time = max(float(d["time"][-1]) for d in self.datasets)
        if max_time <= 0:
            raise ValueError(
                "Detected time data does not span a positive interval.")
        self._setting_scales = True
        self.start_scale.configure(from_=0, to=max_time)
        self.end_scale.configure(from_=0, to=max_time)
        self.start_var.set(0)
        self.end_var.set(max_time)
        self._setting_scales = False

    def _on_span(self, xmin, xmax):
        if not self.datasets or xmin is None or xmax is None:
            return
        lo, hi = sorted((float(xmin), float(xmax)))
        if hi <= lo:
            return
        self._setting_scales = True
        self.start_var.set(lo)
        self.end_var.set(hi)
        self._setting_scales = False
        self._schedule_refit(immediate=True)

    def _schedule_refit(self, immediate=False):
        if self._setting_scales or not self.datasets:
            return
        if self._pending:
            try:
                self.after_cancel(self._pending)
            except tk.TclError:
                pass
        self._pending = self.after(0 if immediate else 300, self._refit_all)

    def _draw_empty(self):
        self.ax.clear()
        self.resax.clear()
        self.label_ax.clear()
        self.label_ax.set_axis_off()
        self.label_ax.text(.02, .98, "Fitted decay values (s)",
                           transform=self.label_ax.transAxes, va="top",
                           fontweight="bold")
        self.ax.set_ylabel("Signal")
        self.resax.set_xlabel("Elapsed time (s)")
        self.resax.set_ylabel("Residual")
        self.ax.set_title(
            "Add one or more files to overlay their decay traces")
        self.fig.tight_layout()
        self.canvas.draw_idle()

    def _refit_all(self):
        self._pending = None
        if not self.datasets:
            return
        lo, hi = sorted((float(self.start_var.get()),
                        float(self.end_var.get())))
        model = self.model_var.get()
        results = []
        for d in self.datasets:
            mask = (d["time"] >= lo) & (d["time"] <= hi)
            try:
                fit = _fit_selected(d["time"][mask], d["signal"][mask], model)
                fit["dataset"] = d
                fit["error"] = None
            except Exception as exc:
                fit = {"dataset": d, "error": str(exc)}
            results.append(fit)
        self.results = results
        self._show_all_results()

    def _show_all_results(self):
        self.results_text.delete("1.0", "end")
        self.ax.clear()
        self.resax.clear()
        self.label_ax.clear()
        self.label_ax.set_axis_off()
        self.label_ax.set_title("Decay values (s)", loc="left", fontsize=10,
                                fontweight="bold")
        colors = ["#2673b8", "#d24c3e", "#31926b", "#8c5aa7",
                  "#d18b23", "#2a9291", "#9a5b42", "#65717e"]
        model = self.model_var.get()
        for i, r in enumerate(self.results):
            d = r["dataset"]
            color = colors[i % len(colors)]
            name = os.path.basename(d["path"])
            t, y = d["time"], d["signal"]
            step = max(1, len(t)//5000)
            self.ax.plot(t[::step], y[::step], ".", ms=2.4,
                         color=color, alpha=.55, label=f"{name} data")
            if r.get("error"):
                self.results_text.insert(
                    "end", f"{name}\n  Could not fit: {r['error']}\n\n")
                label_text = f"{name}\nFit failed"
                self.label_ax.text(
                    .03, .96-i*(.92/max(1, len(self.results))), label_text,
                    transform=self.label_ax.transAxes, va="top",
                    fontsize=max(6, 9-.25*len(self.results)), color=color,
                    wrap=True)
                continue
            p = r["params"]
            m = r["metrics"]
            if model == "Single-exponential":
                decay_text = f"τ = {p[1]:.5g} s"
            elif model == "Bi-exponential":
                decay_text = f"τ₁ = {p[1]:.5g} s\nτ₂ = {p[3]:.5g} s"
            else:
                decay_text = f"τ = {p[1]:.5g} s\nβ = {p[2]:.4g}"
            label_text = f"{name}\n{decay_text}"
            self.label_ax.text(
                .03, .96-i*(.92/max(1, len(self.results))), label_text,
                transform=self.label_ax.transAxes, va="top",
                fontsize=max(6, 9-.25*len(self.results)), color=color,
                wrap=True,
                bbox={"boxstyle": "round,pad=.25", "facecolor": "white",
                      "edgecolor": color, "alpha": .92})
            dense = np.linspace(r["relative_time"][0],
                                r["relative_time"][-1], 500)
            self.ax.plot(dense+r["fit_start"], r["func"](dense, *p),
                         lw=2, color=color, label=f"{name} fit")
            self.resax.plot(r["time"], r["residual"], ".",
                            ms=2.3, color=color, alpha=.7, label=name)
            text = [f"{name}", f"  Sheet: {d['trace']['sheet']}; time: {d['trace']['time_col']}; signal: {d['trace']['signal_col']}",
                    f"  Source unit: {UNIT_LABELS[d['source_unit']]}; fitted points: {len(r['time'])}"]
            if model == "Single-exponential":
                text += [f"  τ = {p[1]:.7g} s; offset = {p[2]:.6g}"]
            elif model == "Bi-exponential":
                a1, t1, a2, t2, c = p
                text += [f"  τ₁ = {t1:.7g} s; A₁ = {a1:.6g}", f"  τ₂ = {t2:.7g} s; A₂ = {a2:.6g}",
                         f"  Amplitude-weighted mean τ = {(a1*t1+a2*t2)/(a1+a2):.7g} s" if a1 +
                         a2 else "  Amplitude-weighted mean τ = n/a",
                         f"  Intensity-weighted mean τ = {(a1*t1*t1+a2*t2*t2)/(a1*t1+a2*t2):.7g} s" if a1 *
                         t1+a2*t2 else "  Intensity-weighted mean τ = n/a",
                         f"  Offset = {c:.6g}"]
            else:
                text += [f"  τ = {p[1]:.7g} s; β = {p[2]:.6g}; offset = {p[3]:.6g}"]
            text += [f"  R² = {m['R²']:.6f}; adjusted R² = {m['Adjusted R²']:.6f}",
                     f"  RMSE = {m['RMSE']:.6g}; AIC = {m['AIC']:.6g}", ""]
            self.results_text.insert("end", "\n".join(text)+"\n")
        self.ax.set_ylabel("Signal / intensity")
        self.ax.set_title(f"{model} fits — all loaded files")
        self.ax.set_xlabel("Elapsed time (s)")
        self.ax.grid(alpha=.2)
        self.ax.legend(loc="best", fontsize=7)
        self.resax.axhline(0, color="black", lw=.8)
        self.resax.set_xlabel("Elapsed time (s)")
        self.resax.set_ylabel("Residual")
        self.resax.grid(alpha=.2)
        self.fig.tight_layout()
        self.canvas.draw_idle()

    def save_results(self):
        if not self.results:
            messagebox.showinfo("No results", "Add files and fit them first.")
            return
        default = os.path.splitext(self.datasets[0]["path"])[
            0]+"_combined_decay_results.xlsx"
        out = filedialog.asksaveasfilename(title="Save combined fit results", initialfile=os.path.basename(
            default), initialdir=os.path.dirname(default), defaultextension=".xlsx", filetypes=[("Excel workbook", "*.xlsx")])
        if not out:
            return
        try:
            summary = []
            curve_rows = []
            model = self.model_var.get()
            for r in self.results:
                d = r["dataset"]
                base = {"File": os.path.basename(d["path"]), "Sheet": d["trace"]["sheet"], "Time column": d["trace"]["time_col"],
                        "Signal column": d["trace"]["signal_col"], "Source unit": UNIT_LABELS[d["source_unit"]], "Model": model}
                if r.get("error"):
                    summary.append(
                        {**base, "Status": "Fit failed", "Error": r["error"]})
                    for t, y in zip(d["time"], d["signal"]):
                        curve_rows.append({**base, "Elapsed time (s)": t, "Observed": y,
                                          "Selected for fit": False, "Fit": np.nan, "Residual": np.nan})
                    continue
                p = r["params"]
                m = r["metrics"]
                row = {**base, "Status": "Fit complete",
                       "Fit start (s)": r["time"][0], "Fit end (s)": r["time"][-1], "Fit points": len(r["time"]), **m}
                if model == "Single-exponential":
                    row.update({"Tau (s)": p[1], "Offset": p[2]})
                elif model == "Bi-exponential":
                    a1, t1, a2, t2, c = p
                    row.update({"A1": a1, "Tau1 (s)": t1, "A2": a2, "Tau2 (s)": t2, "Offset": c, "Amplitude-weighted mean tau (s)": (a1*t1+a2*t2)/(
                        a1+a2) if a1+a2 else np.nan, "Intensity-weighted mean tau (s)": (a1*t1*t1+a2*t2*t2)/(a1*t1+a2*t2) if a1*t1+a2*t2 else np.nan})
                else:
                    row.update({"Tau (s)": p[1], "Beta": p[2], "Offset": p[3]})
                summary.append(row)
                dtime, dy = d["time"], d["signal"]
                selected = (dtime >= r["time"][0]) & (dtime <= r["time"][-1])
                pred = np.full(len(dtime), np.nan)
                residual = np.full(len(dtime), np.nan)
                pred[selected] = r["func"](dtime[selected]-r["fit_start"], *p)
                residual[selected] = dy[selected]-pred[selected]
                for t, y, sel, yp, yr in zip(dtime, dy, selected, pred, residual):
                    curve_rows.append({**base, "Elapsed time (s)": t, "Observed": y,
                                      "Selected for fit": bool(sel), "Fit": yp, "Residual": yr})
            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                pd.DataFrame(summary).to_excel(
                    writer, sheet_name="Fit summary", index=False)
                pd.DataFrame(curve_rows).to_excel(
                    writer, sheet_name="Fitted data", index=False)
            messagebox.showinfo(
                "Saved", f"Combined fit summary and fitted data saved to:\n{out}")
        except Exception as exc:
            messagebox.showerror("Could not save results", str(exc))


if __name__ == "__main__":
    if _DEPENDENCY_ERROR:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Packages required", "Install with:\n\npython -m pip install pandas numpy scipy matplotlib openpyxl\n\n"+_DEPENDENCY_ERROR)
        root.destroy()
    else:
        DecayApp().mainloop()
