"""Reaction amount calculator based on the supplied rare-earth synthesis batch record.

Run with Python 3 on Windows/macOS/Linux. The interface uses only the Python
standard library (Tkinter). All composition fractions, molar masses, purity,
stoichiometric ratios, and shell inputs are editable.
"""

import tkinter as tk
from tkinter import ttk, messagebox


class ReactionCalculator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Rare-earth synthesis amount calculator")
        self.geometry("1080x820")
        self.minsize(900, 680)
        self.vars = {}
        self.shell_vars = {}
        self._build_ui()

    def _entry(self, parent, key, label, default, row, col=0, width=13, unit=""):
        ttk.Label(parent, text=label).grid(
            row=row, column=col, sticky="w", padx=(8, 4), pady=4)
        var = tk.StringVar(value=str(default))
        self.vars[key] = var
        ttk.Entry(parent, textvariable=var, width=width).grid(
            row=row, column=col + 1, sticky="w", padx=4, pady=4)
        if unit:
            ttk.Label(parent, text=unit).grid(
                row=row, column=col + 2, sticky="w", padx=(2, 8), pady=4)
        return var

    def _build_ui(self):
        intro = ttk.Label(
            self,
            text="Enter planned values, then calculate. Masses include the precursor purity correction.",
            padding=(12, 10),
        )
        intro.pack(anchor="w")
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        core = ttk.Frame(notebook, padding=8)
        shell = ttk.Frame(notebook, padding=8)
        notebook.add(core, text="Core recipe")
        notebook.add(shell, text="CaF₂ shell")
        self._build_core_tab(core)
        self._build_shell_tab(shell)

    def _build_core_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        composition = ttk.LabelFrame(
            parent, text="Batch scale and rare-earth composition", padding=8)
        composition.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        self._entry(composition, "total_re",
                    "Total rare-earth amount", 1.00, 0, unit="mmol")
        ttk.Label(composition, text="Fractions (% of total RE; Y is calculated as the balance)").grid(
            row=0, column=3, columnspan=3, sticky="w", padx=14
        )

        reagents = ttk.LabelFrame(
            parent, text="Rare-earth precursors", padding=8)
        reagents.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        headers = ["Element", "Fraction %", "Molar mass g/mol", "Purity %"]
        for j, h in enumerate(headers):
            ttk.Label(reagents, text=h).grid(
                row=0, column=j, sticky="w", padx=8, pady=3)
        rows = [
            ("Er", "er_pct", 2.0, "er_mw", 381.71, "er_purity", 100.0),
            ("Yb", "yb_pct", 18.0, "yb_mw", 387.49, "yb_purity", 100.0),
            ("Ce", "ce_pct", 0.0, "ce_mw", 372.58, "ce_purity", 100.0),
            ("Other RE", "other_pct", 0.0, "other_mw",
             303.36, "other_purity", 100.0),
        ]
        for r, (name, pctkey, pct, mwkey, mw, purkey, purity) in enumerate(rows, start=1):
            ttk.Label(reagents, text=name).grid(
                row=r, column=0, sticky="w", padx=8, pady=3)
            for c, (key, default) in enumerate(((pctkey, pct), (mwkey, mw), (purkey, purity)), start=1):
                var = tk.StringVar(value=str(default))
                self.vars[key] = var
                ttk.Entry(reagents, textvariable=var, width=15).grid(
                    row=r, column=c, sticky="w", padx=8, pady=3)
        ttk.Label(reagents, text="Y (balance)").grid(
            row=5, column=0, sticky="w", padx=8, pady=3)
        self.y_fraction_label = ttk.Label(reagents, text="80.00 %")
        self.y_fraction_label.grid(row=5, column=1, sticky="w", padx=8, pady=3)
        ttk.Label(reagents, text="303.36").grid(
            row=5, column=2, sticky="w", padx=8, pady=3)
        self._entry(reagents, "y_mw", "Y precursor molar mass",
                    303.36, 6, col=0, width=15, unit="g/mol")
        self._entry(reagents, "y_purity", "Y precursor purity",
                    100.0, 6, col=3, width=15, unit="%")
        note = ttk.Label(
            reagents,
            text="Default masses: ErCl₃·6H₂O, YbCl₃·6H₂O, CeCl₃·7H₂O, YCl₃·6H₂O. Edit molar mass for your actual hydrate/formula.",
            wraplength=990,
        )
        note.grid(row=7, column=0, columnspan=4,
                  sticky="w", padx=8, pady=(6, 2))

        base = ttk.LabelFrame(
            parent, text="Other core reagents and solvent defaults", padding=8)
        base.grid(row=2, column=0, sticky="new", padx=4, pady=4)
        fields = [
            ("na_ratio", "NaOH mmol per mmol total RE", 2.50, "mmol/mmol"),
            ("na_mw", "NaOH molar mass", 40.00, "g/mol"),
            ("na_purity", "NaOH purity", 100.0, "%"),
            ("f_ratio", "NH₄F mmol per mmol total RE", 4.00, "mmol/mmol"),
            ("f_mw", "NH₄F molar mass", 37.037, "g/mol"),
            ("f_purity", "NH₄F purity", 100.0, "%"),
            ("oa_ml", "Oleic acid default volume", 6.0, "mL"),
            ("ode_ml", "ODE default volume", 15.0, "mL"),
            ("methanol_ml", "Methanol default volume", 10.0, "mL"),
        ]
        for i, (key, label, value, unit) in enumerate(fields):
            r, c = divmod(i, 3)
            self._entry(base, key, label, value, r, c * 3, width=10, unit=unit)
        ttk.Label(
            base,
            text="Solvent volumes scale linearly with total RE relative to the 1.00 mmol protocol batch; adjust them for your flask and mixing needs.",
            wraplength=990,
        ).grid(row=3, column=0, columnspan=9, sticky="w", padx=8, pady=(5, 2))

        controls = ttk.Frame(parent)
        controls.grid(row=3, column=0, sticky="ew", padx=4, pady=4)
        ttk.Button(controls, text="Calculate core amounts",
                   command=self.calculate_core).pack(side="left", padx=4)
        self.core_output = tk.Text(
            controls.master, height=13, wrap="word", font=("Consolas", 10))
        self.core_output.grid(row=4, column=0, sticky="nsew", padx=4, pady=4)
        parent.rowconfigure(4, weight=1)

    def _build_shell_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        inputs = ttk.LabelFrame(
            parent, text="Recovered core and material assumptions", padding=8)
        inputs.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        entries = [
            ("core_mass", "Recovered dry core mass", 30.0, "mg"),
            ("core_diameter", "Measured inorganic core diameter", 40.0, "nm"),
            ("core_mw", "Core formula mass (equivalent)", 187.89, "g/mol"),
            ("core_density", "Core density", 4.20, "g/cm³"),
            ("caf2_density", "CaF₂ density", 3.18, "g/cm³"),
            ("cacl2_mw", "Anhydrous CaCl₂ molar mass", 110.98, "g/mol"),
            ("caf2_nh4f_mw", "NH₄F molar mass", 37.037, "g/mol"),
            ("cacl2_purity", "CaCl₂ purity", 100.0, "%"),
            ("caf2_nh4f_purity", "NH₄F purity", 100.0, "%"),
            ("stock_conc", "NH₄F feed stock concentration", 0.0, "mmol/mL (0 = omit)"),
        ]
        for i, (key, label, value, unit) in enumerate(entries):
            r, c = divmod(i, 2)
            self._entry(inputs, key, label, value, r,
                        c * 3, width=12, unit=unit)

        increments = ttk.LabelFrame(
            parent, text="Additional radial increments to include", padding=8)
        increments.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        self.shell_vars = {}
        for i, (label, default) in enumerate((("0 → 1 nm", True), ("1 → 2 nm", True), ("2 → 3 nm", True))):
            var = tk.BooleanVar(value=default)
            self.shell_vars[i] = var
            ttk.Checkbutton(increments, text=label, variable=var).grid(
                row=0, column=i, sticky="w", padx=18, pady=4)
        ttk.Label(
            increments,
            text="Each checked row is an additional dose. The NH₄F amount is twice the CaCl₂ amount, matching the record.",
            wraplength=990,
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=5)

        ttk.Button(parent, text="Calculate CaF₂ charges", command=self.calculate_shell).grid(
            row=2, column=0, sticky="w", padx=8, pady=7
        )
        self.shell_output = tk.Text(
            parent, height=17, wrap="word", font=("Consolas", 10))
        self.shell_output.grid(row=3, column=0, sticky="nsew", padx=4, pady=4)
        parent.rowconfigure(3, weight=1)
        ttk.Label(
            parent,
            text="Model: spherical cores; shell formula units estimated from shell/core volume and the entered bulk densities. Assumes the measured diameter is inorganic core diameter. Nominal charge target is not measured shell thickness.",
            wraplength=1000,
        ).grid(row=4, column=0, sticky="w", padx=8, pady=6)

    def _num(self, key):
        raw = self.vars[key].get().strip()
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(
                f"Enter a numeric value for {key.replace('_', ' ')}.") from exc
        return value

    @staticmethod
    def _mass_mg(mmol, mw, purity):
        if purity <= 0 or purity > 100:
            raise ValueError(
                "Purity must be greater than 0 and no more than 100%.")
        if mw <= 0:
            raise ValueError("Molar masses must be greater than zero.")
        return mmol * mw / purity * 100.0

    def calculate_core(self):
        try:
            total = self._num("total_re")
            if total <= 0:
                raise ValueError(
                    "Total rare-earth amount must be greater than zero.")
            species = [
                ("Er", "er_pct", "er_mw", "er_purity"),
                ("Yb", "yb_pct", "yb_mw", "yb_purity"),
                ("Ce", "ce_pct", "ce_mw", "ce_purity"),
                ("Other RE", "other_pct", "other_mw", "other_purity"),
            ]
            fractions = []
            for name, pctkey, mwkey, puritykey in species:
                pct, mw, purity = self._num(pctkey), self._num(
                    mwkey), self._num(puritykey)
                if pct < 0:
                    raise ValueError(f"{name} fraction cannot be negative.")
                fractions.append((name, pct, mw, purity))
            occupied = sum(item[1] for item in fractions)
            y_pct = 100.0 - occupied
            if y_pct < -1e-8:
                raise ValueError(
                    "Er + Yb + Ce + Other RE fractions exceed 100%.")
            y_pct = max(0.0, y_pct)
            y_mw, y_purity = self._num("y_mw"), self._num("y_purity")
            self.y_fraction_label.config(text=f"{y_pct:.3f} %")

            lines = [
                f"CORE BATCH — total rare earth: {total:.5g} mmol", "", "Rare-earth precursor charges:"]
            charged = []
            for name, pct, mw, purity in fractions + [("Y (balance)", y_pct, y_mw, y_purity)]:
                mmol = total * pct / 100.0
                mg = self._mass_mg(mmol, mw, purity) if mmol else 0.0
                charged.append((name, pct, mmol, mg))
                if pct:
                    lines.append(
                        f"  {name:13s} {pct:8.3f}% | {mmol:10.5f} mmol | {mg:9.3f} mg")
            lines += [f"  Sum of RE fractions: {occupied + y_pct:.3f}%", ""]

            for label, amount_key, mw_key, purity_key in (
                ("NaOH", "na_ratio", "na_mw", "na_purity"),
                ("NH₄F", "f_ratio", "f_mw", "f_purity"),
            ):
                ratio, mw, purity = self._num(amount_key), self._num(
                    mw_key), self._num(purity_key)
                if ratio < 0:
                    raise ValueError(
                        "Stoichiometric ratios cannot be negative.")
                mmol = ratio * total
                lines.append(
                    f"{label}: {mmol:.5f} mmol  |  {self._mass_mg(mmol, mw, purity):.3f} mg")
            scale = total / 1.0
            lines += ["",
                      f"Solvent defaults scaled by {scale:.4g}× from the 1.00 mmol recipe (not stoichiometric):"]
            for label, key in (("Oleic acid", "oa_ml"), ("1-octadecene", "ode_ml"), ("Methanol", "methanol_ml")):
                amount = self._num(key)
                if amount < 0:
                    raise ValueError("Solvent volumes cannot be negative.")
                lines.append(f"  {label}: {amount * scale:.3f} mL")
            lines += ["", "Masses are purity-corrected: mmol × g/mol ÷ purity fraction. Verify precursor formula/hydration and supplier assay before weighing."]
            self.core_output.delete("1.0", "end")
            self.core_output.insert("1.0", "\n".join(lines))
        except ValueError as exc:
            messagebox.showerror("Check inputs", str(exc))

    def calculate_shell(self):
        try:
            mass_mg = self._num("core_mass")
            diameter = self._num("core_diameter")
            core_mw = self._num("core_mw")
            rho_core = self._num("core_density")
            rho_shell = self._num("caf2_density")
            cacl2_mw = self._num("cacl2_mw")
            nh4f_mw = self._num("caf2_nh4f_mw")
            cpurity = self._num("cacl2_purity")
            fpurity = self._num("caf2_nh4f_purity")
            concentration = self._num("stock_conc")
            if min(mass_mg, diameter, core_mw, rho_core, rho_shell, cacl2_mw, nh4f_mw) <= 0:
                raise ValueError(
                    "Core mass, diameter, molar masses, and densities must be greater than zero.")
            if concentration < 0:
                raise ValueError("Stock concentration cannot be negative.")
            core_mmol = mass_mg / core_mw
            radius = diameter / 2.0
            lines = [
                f"CaF₂ shell basis: {mass_mg:.4g} mg recovered core; {diameter:.4g} nm diameter",
                f"Equivalent core amount from entered formula mass: {core_mmol:.6f} mmol",
                "", "Additional reagent charges by selected increment:"
            ]
            rows = [(0, 1), (1, 2), (2, 3)]
            total_f = 0.0
            any_selected = False
            for i, (r0, r1) in enumerate(rows):
                if not self.shell_vars[i].get():
                    continue
                any_selected = True
                shell_ratio = ((radius + r1) ** 3 -
                               (radius + r0) ** 3) / radius**3
                # Convert volume ratio to formula-unit amount using the entered bulk densities.
                caf2_mmol = core_mmol * shell_ratio * \
                    (rho_shell / 78.074) / (rho_core / core_mw)
                nh4f_mmol = 2.0 * caf2_mmol
                ca_mg = self._mass_mg(caf2_mmol, cacl2_mw, cpurity)
                f_mg = self._mass_mg(nh4f_mmol, nh4f_mw, fpurity)
                total_f += nh4f_mmol
                lines.append(
                    f"  {r0}→{r1} nm: CaCl₂ {caf2_mmol:.5f} mmol, {ca_mg:.3f} mg | NH₄F {nh4f_mmol:.5f} mmol, {f_mg:.3f} mg")
            if not any_selected:
                raise ValueError("Select at least one radial increment.")
            lines.append(
                f"\nTotal NH₄F for selected increments: {total_f:.5f} mmol")
            if concentration > 0:
                lines.append(
                    f"NH₄F feed volume at {concentration:g} mmol/mL: {total_f / concentration:.3f} mL")
            else:
                lines.append(
                    "Enter an NH₄F stock concentration to calculate feed volume.")
            lines += ["", "Assumptions: spherical, monodisperse cores; entered bulk densities; no correction for dopants, residual ligands, porosity, or incomplete reaction. Each increment is an additional dose. The calculated thickness is a nominal charge target, not a measured shell thickness."]
            self.shell_output.delete("1.0", "end")
            self.shell_output.insert("1.0", "\n".join(lines))
        except ValueError as exc:
            messagebox.showerror("Check inputs", str(exc))


if __name__ == "__main__":
    ReactionCalculator().mainloop()
