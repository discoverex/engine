from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from discoverex.models.types import LogicalStructure, ModelHandle, PhysicalMetadata


class Moondream2Adapter:
    """
    Phase 3: Logical scene graph extraction using Moondream2 (4-bit quantized VLM).

    VRAM lifecycle: load() → extract() → unload()
    Context-Aware Prompting: Phase 1 coordinates are injected into the prompt
    so the model anchors its spatial reasoning to known object positions.
    Graph metrics (hop, diameter, degree) are computed via NetworkX on CPU.
    degree_map = undirected degree of Moondream2 scene graph (logical_degree).
    visual_degree (alpha_degree_map) is separate — sourced from Phase 1.
    """

    def __init__(
        self,
        model_id: str = "vikhyat/moondream2",
        quantization: str = "4bit",
        device: str = "cuda",
        dtype: str = "float16",
    ) -> None:
        self._model_id = model_id
        self._quantization = quantization
        self._device = device
        self._dtype = dtype
        self._model: Any = None
        self._tokenizer: Any = None

    # ------------------------------------------------------------------

    def load(self, handle: ModelHandle) -> None:  # noqa: ARG002
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        quant_cfg = None
        if self._quantization == "4bit":
            quant_cfg = BitsAndBytesConfig(  # type: ignore[no-untyped-call]
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
            )

        self._tokenizer = AutoTokenizer.from_pretrained(  # type: ignore[no-untyped-call]
            self._model_id, trust_remote_code=True
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            self._model_id,
            trust_remote_code=True,
            quantization_config=quant_cfg,
            device_map=self._device if quant_cfg is None else "auto",
        )
        self._model.eval()

    def extract(
        self, composite_image: Path, physical: PhysicalMetadata
    ) -> LogicalStructure:
        from PIL import Image

        image = Image.open(composite_image).convert("RGB")
        prompt = self._build_prompt(physical)
        response = self._query_model(image, prompt)
        relations = self._parse_relations(response)
        return self._build_graph(relations, physical)

    def unload(self) -> None:
        import gc

        import torch

        del self._model
        del self._tokenizer
        self._model = None
        self._tokenizer = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_prompt(self, physical: PhysicalMetadata) -> str:
        obj_desc = "; ".join(
            f"{r['obj_id']} at bbox {r['bbox']}" for r in physical.regions
        )
        return (
            f"The scene contains these objects: {obj_desc}. "
            "For each pair of objects, describe their spatial and logical relationship. "
            "Reply as a JSON array: "
            '[{"subject": "obj_id", "predicate": "relation", "object": "obj_id"}, ...]'
        )

    def _query_model(self, image: Any, prompt: str) -> str:
        # Moondream2 custom API: encode_image → answer_question
        with __import__("torch").no_grad():
            enc_image = self._model.encode_image(image)
            answer = self._model.answer_question(enc_image, prompt, self._tokenizer)
        return answer if isinstance(answer, str) else str(answer)

    def _parse_relations(self, response: str) -> list[dict[str, Any]]:
        # Extract JSON array from free-form model response
        match = re.search(r"\[.*\]", response, re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group())
            return [r for r in data if isinstance(r, dict)]
        except json.JSONDecodeError:
            return []

    def _build_graph(
        self, relations: list[dict[str, Any]], physical: PhysicalMetadata
    ) -> LogicalStructure:
        import networkx as nx

        g: nx.DiGraph = nx.DiGraph()
        obj_ids = [r["obj_id"] for r in physical.regions]
        g.add_nodes_from(obj_ids)

        for rel in relations:
            subj = rel.get("subject", "")
            obj = rel.get("object", "")
            if subj and obj and subj in obj_ids and obj in obj_ids:
                g.add_edge(subj, obj, predicate=rel.get("predicate", ""))

        # Hop from root = longest shortest path from any source node (in_degree == 0)
        root_candidates = [n for n in g.nodes if g.in_degree(n) == 0] or list(g.nodes)[
            :1
        ]
        hop_map: dict[str, int] = {}
        for node in g.nodes:
            hops = []
            for root in root_candidates:
                try:
                    hops.append(nx.shortest_path_length(g, root, node))
                except nx.NetworkXNoPath:
                    pass
            hop_map[node] = max(hops, default=0)

        ug = g.to_undirected()
        try:
            diameter = (
                float(nx.diameter(ug))
                if len(ug) > 0 and nx.is_connected(ug)
                else float(len(ug))
            )
        except nx.NetworkXError:
            diameter = float(
                max(len(c) for c in nx.connected_components(ug)) if ug else 1
            )

        # logical_degree = Moondream2 scene graph의 undirected 연결 차수
        degree_map: dict[str, int] = {node: ug.degree(node) for node in ug.nodes}

        return LogicalStructure(
            relations=relations,
            degree_map=degree_map,
            hop_map=hop_map,
            diameter=max(diameter, 1.0),
        )
