"""Draw the lineage of the dbt project (sources -> silver -> gold -> consumers) from its manifest.json.

    python data/dbt/scripts/lineage_diagram.py MANIFEST.json OUT_DIR

Writes lineage.svg, lineage.png and lineage.dot. Needs the Graphviz `dot` program. The manifest is the one
`dbt docs generate` writes, and the pipeline stores the latest at <lake>/docs/latest/manifest.json.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

LAYERS = [
    # (key, title, fill, border)
    ("source", "Bronze: archivos de S3 cargados en DuckDB", "#FEF7E0", "#F9AB00"),
    ("silver", "Silver: vistas limpias (dbt)", "#E8F0FE", "#4285F4"),
    ("gold", "Gold: tablas publicadas en Cloud SQL", "#E6F4EA", "#34A853"),
    ("consumer", "Quién lo lee", "#F3E8FD", "#A142F4"),
]
STYLE = {key: (fill, border) for key, _, fill, border in LAYERS}


def short(unique_id: str) -> str:
    return unique_id.split(".")[-1]


def layer_of(unique_id: str, nodes: dict) -> str:
    if unique_id.startswith("source."):
        return "source"
    if unique_id.startswith("exposure."):
        return "consumer"
    schema = nodes[unique_id]["schema"]
    return "gold" if schema.endswith("gold") else "silver"


def build_dot(manifest: dict) -> str:
    models = {k: v for k, v in manifest["nodes"].items() if v["resource_type"] == "model"}
    sources = manifest["sources"]
    exposures = manifest.get("exposures", {})
    every = {**models, **sources, **exposures}

    tests_on = {}
    for test in (v for v in manifest["nodes"].values() if v["resource_type"] == "test"):
        for parent in test.get("depends_on", {}).get("nodes", []):
            tests_on[parent] = tests_on.get(parent, 0) + 1

    def label(unique_id: str) -> str:
        node = every[unique_id]
        name = node.get("label") or short(unique_id)
        if unique_id.startswith("exposure."):
            return f"{name}\\n(aplicación)"
        if unique_id.startswith("source."):
            return name  # the columns a source declares are not the columns of the loaded table
        columns = len(node.get("columns", {}))
        tests = tests_on.get(unique_id, 0)
        detail = f"{columns} columnas" if columns else ""
        if tests:
            detail += f" · {tests} pruebas" if detail else f"{tests} pruebas"
        return f"{name}\\n{detail}" if detail else name

    lines = [
        "digraph lineage {",
        '  rankdir=LR; compound=true; splines=true; nodesep=0.18; ranksep=1.3; pad=0.4;',
        '  labelloc=t; fontsize=20; fontname="Helvetica-Bold";',
        '  label="Linaje de datos: S3 → bronze → silver → gold → consumidores";',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, margin="0.14,0.07"];',
        '  edge [color="#5F6368", arrowsize=0.7];',
    ]
    for key, title, fill, border in LAYERS:
        members = [u for u in every if layer_of(u, manifest["nodes"]) == key]
        if not members:
            continue
        lines.append(f'  subgraph cluster_{key} {{ label="{title}"; style="rounded,filled"; fillcolor="{fill}"; '
                     f'color="{border}"; fontname="Helvetica-Bold"; fontsize=13;')
        for unique_id in sorted(members):
            wide = "penwidth=2.2, " if key == "gold" else ""
            lines.append(f'    "{unique_id}" [label="{label(unique_id)}", fillcolor="white", color="{border}", {wide}];')
        lines.append("  }")

    for child, parents in manifest["parent_map"].items():
        if child not in every:
            continue
        for parent in parents:
            if parent in every:
                lines.append(f'  "{parent}" -> "{child}";')
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv: list) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    manifest = json.loads(Path(argv[1]).read_text())
    out = Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    dot = shutil.which("dot")
    if not dot:
        print("Graphviz `dot` is not installed", file=sys.stderr)
        return 1
    source = out / "lineage.dot"
    source.write_text(build_dot(manifest))
    for fmt in ("svg", "png"):
        subprocess.run([dot, f"-T{fmt}", "-Gdpi=130", str(source), "-o", str(out / f"lineage.{fmt}")], check=True)
    print(f"wrote {out}/lineage.svg, .png and .dot")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
