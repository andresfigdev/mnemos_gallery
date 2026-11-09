"""
Actualiza ckpt_name y nodos LoraLoader en copias de prompt_json / workflow_json.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _mutate_nodes(nodes: Optional[Dict[str, Any]], model_name: Optional[str], loras: Optional[List[Dict[str, Any]]]) -> None:
    if not nodes or not isinstance(nodes, dict):
        return

    lora_nodes: List[Dict[str, Any]] = []
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type", "")
        if ct in ("CheckpointLoaderSimple", "CheckpointLoader"):
            if model_name is not None:
                ins = node.setdefault("inputs", {})
                if model_name.strip():
                    ins["ckpt_name"] = model_name.strip()
                else:
                    ins.pop("ckpt_name", None)
        if ct in ("LoraLoader", "LoraLoaderModelOnly"):
            lora_nodes.append(node)

    if loras is not None:
        # Actualizar nodos existentes por orden; si hay más nodos que loras, limpiar nombres sobrantes
        for i, node in enumerate(lora_nodes):
            ins = node.setdefault("inputs", {})
            if i < len(loras):
                entry = loras[i]
                name = (entry.get("name") or "").strip()
                if name:
                    ins["lora_name"] = name
                    if "strength" in entry and entry["strength"] is not None:
                        ins["strength"] = entry["strength"]
                    if "strength_model" in entry and entry["strength_model"] is not None:
                        ins["strength_model"] = entry["strength_model"]
                else:
                    ins.pop("lora_name", None)
            else:
                ins.pop("lora_name", None)


def apply_model_and_loras(
    prompt_json: Optional[Dict[str, Any]],
    workflow_json: Optional[Dict[str, Any]],
    model_name: Optional[str] = None,
    loras: Optional[List[Dict[str, Any]]] = None,
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Devuelve (prompt_json_new, workflow_json_new) copias profundas con mutaciones.
    model_name / loras None => no cambiar ese aspecto.
    """
    pj = copy.deepcopy(prompt_json) if prompt_json else None
    wj = copy.deepcopy(workflow_json) if workflow_json else None
    try:
        if model_name is not None:
            _mutate_nodes(pj, model_name, None)
            _mutate_nodes(wj, model_name, None)
        if loras is not None:
            _mutate_nodes(pj, None, loras)
            _mutate_nodes(wj, None, loras)
    except Exception as e:
        logger.error("Error mutando workflow JSON: %s", e, exc_info=True)
        raise
    return pj, wj
