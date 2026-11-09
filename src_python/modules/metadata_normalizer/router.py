"""
Router - Endpoints API para el módulo Metadata Normalizer
Paso 9.3 - Router para reemplazos
Rutas: /api/normalizer/*
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from pydantic import BaseModel, Field

from .regex_service import RegexService

router = APIRouter(prefix="/api/normalizer", tags=["normalizer"])

# Instancia global del servicio (en producción podría ser un singleton o inyectado)
regex_service = RegexService()


class ReplacementRule(BaseModel):
    """Modelo para una regla de reemplazo"""
    pattern: str = Field(..., description="Patrón regex a buscar")
    replacement: str = Field(..., description="Texto de reemplazo")
    flags: int = Field(0, description="Flags de regex (0 = sin flags)")
    description: Optional[str] = Field(None, description="Descripción opcional de la regla")


class NormalizeRequest(BaseModel):
    """Request model para normalizar texto"""
    text: str = Field(..., description="Texto a normalizar")
    rules: Optional[List[ReplacementRule]] = Field(None, description="Reglas opcionales a aplicar (si no se proporcionan, usa las reglas del servicio)")


class NormalizeResponse(BaseModel):
    """Response model para normalización"""
    original: str
    normalized: str
    replacements: List[dict]


class NormalizeBatchRequest(BaseModel):
    """Request model para normalizar múltiples textos"""
    texts: List[str] = Field(..., description="Lista de textos a normalizar")
    rules: Optional[List[ReplacementRule]] = Field(None, description="Reglas opcionales a aplicar")


class NormalizeBatchResponse(BaseModel):
    """Response model para normalización en lote"""
    results: List[NormalizeResponse]


@router.post("/normalize", response_model=NormalizeResponse)
async def normalize_text(request: NormalizeRequest):
    """
    Normaliza un texto aplicando reglas de reemplazo regex
    
    Si se proporcionan reglas en el request, se usan esas.
    Si no, se usan las reglas configuradas en el servicio.
    """
    try:
        rules = None
        if request.rules:
            rules = [rule.model_dump() for rule in request.rules]
        
        result = regex_service.normalize_text(request.text, rules)
        return NormalizeResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al normalizar texto: {str(e)}"
        )


@router.post("/normalize/batch", response_model=NormalizeBatchResponse)
async def normalize_batch(request: NormalizeBatchRequest):
    """
    Normaliza múltiples textos aplicando reglas de reemplazo regex
    """
    try:
        rules = None
        if request.rules:
            rules = [rule.model_dump() for rule in request.rules]
        
        results = regex_service.normalize_batch(request.texts, rules)
        return NormalizeBatchResponse(
            results=[NormalizeResponse(**result) for result in results]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al normalizar textos: {str(e)}"
        )


@router.get("/rules", response_model=List[ReplacementRule])
async def get_rules():
    """
    Obtiene todas las reglas de reemplazo configuradas
    """
    try:
        rules = regex_service.get_replacement_rules()
        return [ReplacementRule(**rule) for rule in rules]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener reglas: {str(e)}"
        )


@router.post("/rules", response_model=ReplacementRule, status_code=status.HTTP_201_CREATED)
async def add_rule(rule: ReplacementRule):
    """
    Agrega una nueva regla de reemplazo
    """
    try:
        # Validar que el patrón regex sea válido
        import re
        try:
            re.compile(rule.pattern, rule.flags)
        except re.error as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Patrón regex inválido: {str(e)}"
            )
        
        added_rule = regex_service.add_replacement_rule(
            pattern=rule.pattern,
            replacement=rule.replacement,
            flags=rule.flags,
            description=rule.description
        )
        return ReplacementRule(**added_rule)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al agregar regla: {str(e)}"
        )


@router.delete("/rules/{pattern:path}")
async def delete_rule(pattern: str):
    """
    Elimina una regla de reemplazo por su patrón
    
    Nota: El patrón debe estar URL-encoded si contiene caracteres especiales
    """
    try:
        # Decodificar el patrón si está URL-encoded
        from urllib.parse import unquote
        decoded_pattern = unquote(pattern)
        
        removed = regex_service.remove_replacement_rule(decoded_pattern)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Regla con patrón '{decoded_pattern}' no encontrada"
            )
        
        return {"message": f"Regla '{decoded_pattern}' eliminada correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar regla: {str(e)}"
        )

