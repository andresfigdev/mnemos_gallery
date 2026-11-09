"""
Extrae modelo y LoRAs desde prompt_json / workflow_json guardados en BD (sin tablas satélite).
resource_id=0 indica dato embebido (no hay catálogo local).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from .metadata_service import LoraInfo


def _iter_nodes(data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not data or not isinstance(data, dict):
        return []
    return [n for n in data.values() if isinstance(n, dict)]


def extract_model_and_loras_from_json(
    prompt_json: Optional[Dict[str, Any]],
    workflow_json: Optional[Dict[str, Any]],
) -> Tuple[Optional[str], List[LoraInfo]]:
    """Replica la lógica mínima de extracción Comfy desde dicts ya parseados."""
    for source in (prompt_json, workflow_json):
        model_name: Optional[str] = None
        loras: List[LoraInfo] = []
        for node in _iter_nodes(source):
            class_type = node.get("class_type", "")
            inputs = node.get("inputs") or {}
            if class_type in ("CheckpointLoaderSimple", "CheckpointLoader"):
                ckpt = inputs.get("ckpt_name")
                if isinstance(ckpt, str) and ckpt.strip():
                    model_name = ckpt.strip()
            if class_type in ("LoraLoader", "LoraLoaderModelOnly"):
                lora_name = inputs.get("lora_name")
                if isinstance(lora_name, str) and lora_name.strip():
                    loras.append(
                        LoraInfo(
                            name=lora_name.strip(),
                            strength=inputs.get("strength"),
                            strength_model=inputs.get("strength_model"),
                        )
                    )
        if model_name or loras:
            return model_name, loras
    return None, []


EMBEDDED_RESOURCE_ID = 0


def build_linked_payload(
    prompt_json: Optional[Dict[str, Any]],
    workflow_json: Optional[Dict[str, Any]],
) -> Tuple[Optional[dict], List[dict]]:
    """Payload compatible con LinkedResourceInfo (Pydantic) en el router."""
    model_name, loras = extract_model_and_loras_from_json(prompt_json, workflow_json)
    linked_model = None
    if model_name:
        linked_model = {
            "resource_id": EMBEDDED_RESOURCE_ID,
            "nombre": model_name,
            "strength": None,
            "strength_model": None,
        }
    linked_loras = [
        {
            "resource_id": EMBEDDED_RESOURCE_ID,
            "nombre": l.name,
            "strength": float(l.strength) if l.strength is not None else None,
            "strength_model": float(l.strength_model) if l.strength_model is not None else None,
        }
        for l in loras
    ]
    return linked_model, linked_loras
