from __future__ import annotations

import importlib.util
import math
from typing import Any


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def quick_mm(smiles: str | None, seed: int = 42) -> dict[str, Any]:
    if not smiles:
        return {"available": False, "reason": "no SMILES for this candidate"}
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"available": False, "reason": "RDKit could not parse SMILES"}
        mol = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = int(seed)
        conf_id = AllChem.EmbedMolecule(mol, params)
        if conf_id < 0:
            return {"available": False, "reason": "conformer embedding failed"}
        props = AllChem.MMFFGetMoleculeProperties(mol, mmffVariant="MMFF94s")
        if props is None:
            AllChem.UFFOptimizeMolecule(mol, maxIters=500)
            ff = "UFF"
            energy = None
        else:
            ff_obj = AllChem.MMFFGetMoleculeForceField(mol, props)
            ff_obj.Minimize(maxIts=1000)
            energy = ff_obj.CalcEnergy()
            ff = "MMFF94s"
        dist = 0.0
        if mol.GetNumConformers() >= 1:
            conf = mol.GetConformer()
            if mol.GetNumAtoms() > 0:
                dist = math.sqrt(sum((conf.GetAtomPosition(i).x) ** 2 + (conf.GetAtomPosition(i).y) ** 2 + (conf.GetAtomPosition(i).z) ** 2 for i in range(mol.GetNumAtoms())))
        return {
            "available": True,
            "engine": ff,
            "smiles": smiles,
            "atoms_with_h": mol.GetNumAtoms(),
            "energy_kcal_mol": round(float(energy), 3) if energy is not None else None,
            "radius_of_gyration_proxy": round(dist, 3),
            "note": "Fast molecular-mechanics sanity check only; not MD and not a binding free-energy calculation.",
        }
    except Exception as exc:
        return {"available": False, "reason": f"MMFF check failed: {exc}"}


def quick_qm(smiles: str | None, max_heavy_atoms: int = 30) -> dict[str, Any]:
    if not smiles:
        return {"available": False, "reason": "no SMILES for this candidate"}
    if not _has("pyscf"):
        return {
            "available": False,
            "reason": "PySCF is not installed in this environment; the report still contains a reproducible TD-DFT protocol.",
            "install_hint": "pip install pyscf",
        }
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from pyscf import dft, gto
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"available": False, "reason": "RDKit could not parse SMILES"}
        if mol.GetNumHeavyAtoms() > max_heavy_atoms:
            return {"available": False, "reason": f"molecule has {mol.GetNumHeavyAtoms()} heavy atoms; limit is {max_heavy_atoms} for the quick check"}
        mol = Chem.AddHs(mol)
        AllChem.EmbedMolecule(mol, randomSeed=7)
        AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
        conf = mol.GetConformer()
        atom_symbols = [atom.GetSymbol() for atom in mol.GetAtoms()]
        coords = [[conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y, conf.GetAtomPosition(i).z] for i in range(mol.GetNumAtoms())]
        atom = [[symbol, tuple(xyz)] for symbol, xyz in zip(atom_symbols, coords)]
        mol_pyscf = gto.M(atom=atom, basis="sto-3g", verbose=0)
        mf = dft.RKS(mol_pyscf)
        mf.xc = "b3lyp"
        mf.max_cycle = 40
        mf.conv_tol = 1e-5
        energy = mf.kernel()
        mo_energy = mf.mo_energy
        nocc = mol_pyscf.nelectron // 2
        homo = float(mo_energy[nocc - 1])
        lumo = float(mo_energy[nocc])
        return {
            "available": True,
            "engine": "PySCF B3LYP/STO-3G",
            "heavy_atoms": mol.GetNumHeavyAtoms(),
            "scf_energy_hartree": round(float(energy), 6),
            "homo_ev": round(homo * 27.211386245988, 3),
            "lumo_ev": round(lumo * 27.211386245988, 3),
            "gap_ev": round((lumo - homo) * 27.211386245988, 3),
            "note": "Gas-phase single-point sanity check; not TD-DFT, not solvated, not a fluorescence prediction.",
        }
    except Exception as exc:
        return {"available": False, "reason": f"quick QM check failed: {exc}"}


def build_validation_plan(selected: dict[str, Any], brief: dict[str, Any], formulation: dict[str, Any]) -> dict[str, Any]:
    record = selected.get("record", {})
    name = record.get("name", selected.get("name"))
    kind = selected.get("kind", "protein")
    sequence = record.get("sequence")
    smiles = record.get("smiles")
    pdb_id = record.get("pdb_id")
    temp = brief["conditions"]["process_temp_c"]
    ph = brief["conditions"]["ph"]
    retention = selected["metrics"]["overall_retention"]
    quick = quick_mm(smiles, seed=42) if kind == "compound" else {
        "available": False,
        "reason": "A full protein force-field setup requires a PDB/homology model; see the MD protocol.",
    }
    qm = quick_qm(smiles, max_heavy_atoms=30) if kind == "compound" else {
        "available": False,
        "reason": "Protein chromophore QM/MM requires a prepared chromophore-containing model; see the QM/MM protocol.",
    }
    md = {
        "status": "protocol_ready",
        "engines": ["OpenMM 8.x", "AmberTools 25", "GROMACS"],
        "system": f"{name} in explicit or implicit solvent; ligand/protectant parameters as needed",
        "force_fields": ["ff14SB/amber14-all", "GAFF2 or OpenFF for ligands", "TIP3P/OPC water", "GBn2 implicit solvent for a quick scan"],
        "protocol": [
            "Prepare structure: remove crystallographic waters/ligands that are not part of the design, add missing atoms, assign protonation states at the target pH, and cap termini.",
            "Parameterise non-standard chromophore/cofactor and protectants (GAFF2/OpenFF); validate charges and atom types.",
            "Solvate in a dodecahedral box with ≥1.2 nm padding, neutralise, add 0.15 M NaCl; or use GBn2 implicit solvent for a rapid screen.",
            "Energy minimise (steepest descent/conjugate gradient) until the maximum force is below 1000 kJ/mol/nm; relax restraints in stages.",
            "Equilibrate NVT 100 ps and NPT 100 ps at the target temperature/pressure with Langevin thermostat and Monte Carlo barostat.",
            "Run 3 × 100 ns production MD with different seeds; save every 10 ps; keep temperature, pressure, energy and box logs.",
            "Analyse RMSD, RMSF, radius of gyration, SASA, hydrogen bonds, secondary structure, chromophore environment and protectant residence times.",
            "For a ligand/protectant, estimate relative binding or preferential interaction with MM/GBSA or free-energy perturbation; do not over-interpret a single replica.",
            "Repeat at the process temperature and at storage temperature; compare apo vs protectant-bound and neutral vs acid pH.",
        ],
        "acceptance": [
            "Backbone RMSD plateau and no unfolding beyond the calibrated baseline for the same fold.",
            "Chromophore pocket RMSD and key hydrogen-bond occupancy remain within the pre-registered tolerance.",
            "Protectant has favourable preferential-interaction or binding metrics without displacing the chromophore.",
            "Results are consistent across replicas; report mean ± SD, not a single trajectory.",
        ],
        "commands": {
            "openmm": (
                "python - <<'PY'\n"
                "from openmm.app import PDBFile, ForceField, Modeller, Simulation, PME, NoCutoff\n"
                "from openmm import LangevinMiddleIntegrator, Platform, unit\n"
                "pdb = PDBFile('model.pdb')\n"
                "ff = ForceField('amber14-all.xml', 'implicit/gbn2.xml')\n"
                "modeller = Modeller(pdb.topology, pdb.positions)\n"
                "modeller.addHydrogens(ff)\n"
                "system = ff.createSystem(modeller.topology, nonbondedMethod=NoCutoff, constraints=None)\n"
                "integrator = LangevinMiddleIntegrator(300*unit.kelvin, 1/unit.picosecond, 0.002*unit.picoseconds)\n"
                "sim = Simulation(modeller.topology, system, integrator, Platform.getPlatformByName('CPU'))\n"
                "sim.context.setPositions(modeller.positions); sim.minimizeEnergy(maxIterations=1000)\n"
                "sim.step(50000)  # 100 ps; extend to 100 ns for production\n"
                "state = sim.context.getState(getPositions=True, getEnergy=True)\n"
                "print(state.getPotentialEnergy())\n"
                "PY"
            ),
            "amber": "tleap -f leap.in && pmemd.cuda -O -i md.in -o md.out -p system.prmtop -c system.inpcrd -r md.rst7 -x md.nc",
            "gromacs": "gmx_mpi pdb2gmx -f model.pdb -o model.gro -water tip3p -ff amber99sb-ildn && gmx_mpi solvate -cp model.gro -o solv.gro -p topol.top",
        },
        "estimated_cost": "1-3 GPU-days for 3 × 100 ns, depending on system size and hardware; a 10 ns pilot is recommended first.",
        "limitations": "MD is a sampling method, not proof of function. Force-field errors for chromophores and cofactors can be large.",
    }
    qm_plan = {
        "status": "protocol_ready",
        "engines": ["ORCA 5/6", "Gaussian 16", "PySCF", "Q-Chem"],
        "system": "Chromophore/protectant model cluster or QM/MM region around the chromophore",
        "protocol": [
            "Build a chemically sensible chromophore model (e.g., HBI or bilin) with nearby key residues and a solvent shell; cap dangling bonds.",
            "Optimise ground state with B3LYP-D3(BJ)/def2-SVP or ωB97X-D/6-31G* in implicit solvent (CPCM/SMD).",
            "Run frequency calculations to confirm a minimum; correct thermal free energies if comparing tautomers/conformers.",
            "Compute vertical excitations with TD-DFT (CAM-B3LYP/def2-SVP or ωB97X-D/6-31G*) and enough states (≥10) to cover the absorption/emission window.",
            "For emission, optimise the S1 state and compute vertical emission; include implicit solvent and, where feasible, QM/MM embedding.",
            "Compare calculated λmax/λem, oscillator strengths and orbital character with measured spectra; report method-dependent uncertainty.",
            "For protectant interactions, compute interaction energies and relevant excited-state shifts; do not infer food safety from QM.",
        ],
        "acceptance": [
            "Optimised geometry is a true minimum (no imaginary frequencies).",
            "TD-DFT trend reproduces the measured λmax/λem within the pre-registered method uncertainty (typically 0.2-0.4 eV for this class).",
            "Conclusions are robust to at least two functionals/bases or to a QM/MM vs cluster comparison.",
            "Report absolute energies, method, basis, solvent model, number of states and software version.",
        ],
        "commands": {
            "orca_example": (
                "! B3LYP D3BJ def2-SVP CPCM(water) TightSCF\n"
                "%tddft nroots 10 tda false end\n"
                "* xyzfile 0 1 chromophore.xyz\n"
            ),
            "pyscf_example": "from pyscf import gto, dft, tddft; mol=gto.M(atom='chromophore.xyz', basis='def2-svp'); mf=dft.RKS(mol).run(); td=tddft.TDA(mf); td.nstates=10; td.kernel()",
        },
        "estimated_cost": "Minutes to hours for a cluster model; QM/MM and large basis sets can require CPU/GPU days.",
        "limitations": "TD-DFT accuracy depends strongly on functional, solvent model and chromophore environment; QM cannot validate food safety or biological function alone.",
    }
    spectral_plan = {
        "status": "planned",
        "measurements": [
            {"type": "UV-Vis", "method": "1 cm quartz cuvette, matrix blank, 240-700 nm, 25.0 ± 0.5°C", "purpose": "Absorption peak position and intensity; detect aggregation/scattering."},
            {"type": "Steady-state fluorescence", "method": "Fix excitation at the candidate λex, slit widths and detector gain; emission 10 nm above λex to 750 nm; correct for matrix absorbance", "purpose": "Retention, Δλem and spectral shape."},
            {"type": "Excitation spectrum", "method": "Fix emission at λem, scan excitation; correct for lamp profile", "purpose": "Confirm chromophore identity and environment."},
            {"type": "IR/FTIR", "method": "ATR-FTIR or KBr pellet; 4000-400 cm-1; baseline and atmospheric correction", "purpose": "Protein secondary structure and excipient interactions."},
            {"type": "LC-MS", "method": "ESI-MS with representative matrix; report m/z, adducts and fragmentation", "purpose": "Identity and degradation products; not a de novo structure proof."},
            {"type": "NMR", "method": "1H NMR in an appropriate deuterated solvent; water suppression if needed", "purpose": "Small-molecule identity/purity; proteins require advanced multidimensional NMR."},
        ],
        "acceptance": [
            f"Fluorescence retention ≥ {brief['spectral']['target_retention']:.0%} at the target process and shelf-life points.",
            "Δλem ≤ 3 nm and spectral cosine ≥ 0.98 versus the unstressed reference.",
            "UV-Vis peak position shift within the pre-registered tolerance; no new scattering/aggregation signature.",
            "Report instrument, slits, integration time, temperature, blank and number of replicates.",
        ],
        "note": "Spectral invariance must be demonstrated with measured spectra; the model output is only a hypothesis.",
    }
    experimental = {
        "status": "planned",
        "design": "Randomised, blinded, paired design with ≥3 independent batches and ≥3 technical replicates; include unstressed control and matrix blank.",
        "samples": [
            "Control: candidate at target dose in the target matrix, no protectant, same process.",
            "Formulated: optimised protectant blend, same candidate dose and process.",
            "Stress: heat challenge, acid challenge, combined heat+acid, light/oxygen challenge.",
            "Stability: 0, 7, 14, 30, 60 days at 4°C and 25°C; accelerated 40°C/75% RH where appropriate.",
        ],
        "analytics": [
            "Fluorescence retention and full emission spectrum.",
            "UV-Vis absorption and colour (ΔE).",
            "pH, viscosity, turbidity, particle size if relevant.",
            "SDS-PAGE/SEC-HPLC for protein integrity; LC-MS for small-molecule degradation.",
            "Microbial tests and sensory/taste panel for food prototypes.",
        ],
        "statistics": [
            "Report mean ± SD and 95% CI; paired t-test or mixed-effects model for formulation vs control.",
            "Pre-register equivalence margins; do not use p>0.05 as proof of equivalence.",
            "Use a design-of-experiments (DOE) screen for protectant dose and process temperature; avoid one-factor-at-a-time overfitting.",
        ],
        "acceptance": [
            "At least 3 independent batches meet the spectral and retention thresholds.",
            "No unacceptable sensory, colour, viscosity or microbial changes.",
            "All ingredients and process steps pass the local regulatory and safety review.",
        ],
        "limitations": "The lab package is a starting protocol. It must be adapted to the actual expression system, protein construct, matrix and equipment.",
    }
    return {
        "summary": "MD/QM and spectral validation plan generated. Quick MM/QM checks are separate from production simulations and must not be presented as full validation.",
        "quick_checks": {"molecular_mechanics": quick, "quantum_mechanics": qm},
        "md": md,
        "qm": qm_plan,
        "spectra": spectral_plan,
        "experimental": experimental,
        "digital_twin": {
            "status": "computed",
            "predicted_overall_retention": round(retention, 4),
            "target": brief["spectral"]["target_retention"],
            "note": "Prediction is a prior for experiment design, not evidence of real-world stability.",
        },
        "limitations": [
            "No MD/QM production run is executed by this API request; the quick checks are small and optional.",
            "The selected protein may lack an experimental structure; a homology model or AlphaFold model must be prepared and validated.",
            "Force-field, chromophore and solvent errors can change the ranking; treat the output as a hypothesis.",
            "Food safety, allergenicity, toxicity and regulatory compliance are outside the scope of MD/QM.",
        ],
    }
