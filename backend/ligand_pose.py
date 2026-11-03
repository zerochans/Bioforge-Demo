from __future__ import annotations

import json
import sys
from pathlib import Path


def prepare_pose(template_path: Path, pose_path: Path, out_path: Path) -> dict:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    template = Chem.MolFromMolFile(str(template_path), removeHs=False)
    pose = Chem.MolFromPDBFile(str(pose_path), removeHs=False, sanitize=True, proximityBonding=True)
    if template is None:
        raise ValueError("cannot read ligand template SDF")
    if pose is None:
        raise ValueError("cannot read docked pose PDB")
    heavy_template = Chem.RemoveHs(template)
    heavy_pose = Chem.RemoveHs(pose)
    match = heavy_pose.GetSubstructMatch(heavy_template)
    if len(match) != heavy_template.GetNumAtoms():
        raise ValueError("docked pose does not match the ligand template")
    molecule = Chem.RemoveHs(template)
    pose_conf = pose.GetConformer()
    target_conf = molecule.GetConformer()
    for target_index, pose_index in enumerate(match):
        target_conf.SetAtomPosition(target_index, pose_conf.GetAtomPosition(pose_index))
    molecule = Chem.AddHs(molecule, addCoords=True)
    try:
        properties = AllChem.MMFFGetMoleculeProperties(molecule)
        force_field = AllChem.MMFFGetMoleculeForceField(molecule, properties) if properties else None
        if force_field is not None:
            for atom in molecule.GetAtoms():
                if atom.GetAtomicNum() > 1:
                    force_field.AddFixedPoint(atom.GetIdx())
            force_field.Minimize(maxIts=200)
    except Exception:
        pass
    Chem.MolToMolFile(molecule, str(out_path))
    info = {
        "charge": int(Chem.GetFormalCharge(molecule)),
        "atoms": int(molecule.GetNumAtoms()),
        "heavy_atoms": int(molecule.GetNumHeavyAtoms()),
        "smiles": Chem.MolToSmiles(molecule),
    }
    out_path.with_suffix(".json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: ligand_pose.py TEMPLATE_SDF POSE_PDB OUTPUT_SDF", file=sys.stderr)
        return 2
    info = prepare_pose(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
