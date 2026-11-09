"""
Regex Service - Servicio para normalización de metadatos usando regex
Paso 9.3 - Service de regex básico
Permite hacer reemplazos de texto usando expresiones regulares
"""

import re
from typing import Dict, Any, List, Optional


class RegexService:
    """
    Servicio para normalización de metadatos usando expresiones regulares
    Permite definir reglas de reemplazo para normalizar nombres, términos, etc.
    """
    
    def __init__(self):
        """Inicializa el servicio de regex"""
        # Reglas de reemplazo predefinidas (se pueden cargar desde BD después)
        self._replacement_rules: List[Dict[str, Any]] = []
    
    def add_replacement_rule(
        self,
        pattern: str,
        replacement: str,
        flags: int = 0,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Agrega una regla de reemplazo
        
        Args:
            pattern: Patrón regex a buscar
            replacement: Texto de reemplazo
            flags: Flags de regex (re.IGNORECASE, re.MULTILINE, etc.)
            description: Descripción opcional de la regla
        
        Returns:
            Dict con la regla agregada
        """
        rule = {
            "pattern": pattern,
            "replacement": replacement,
            "flags": flags,
            "description": description
        }
        self._replacement_rules.append(rule)
        return rule
    
    def remove_replacement_rule(self, pattern: str) -> bool:
        """
        Elimina una regla de reemplazo por su patrón
        
        Args:
            pattern: Patrón de la regla a eliminar
        
        Returns:
            True si se eliminó, False si no se encontró
        """
        initial_count = len(self._replacement_rules)
        self._replacement_rules = [
            rule for rule in self._replacement_rules
            if rule["pattern"] != pattern
        ]
        return len(self._replacement_rules) < initial_count
    
    def get_replacement_rules(self) -> List[Dict[str, Any]]:
        """
        Obtiene todas las reglas de reemplazo
        
        Returns:
            Lista de reglas de reemplazo
        """
        return self._replacement_rules.copy()
    
    def normalize_text(
        self,
        text: str,
        rules: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Normaliza un texto aplicando las reglas de reemplazo
        
        Args:
            text: Texto a normalizar
            rules: Lista opcional de reglas a aplicar. Si es None, usa las reglas del servicio
        
        Returns:
            Dict con:
            {
                "original": str,
                "normalized": str,
                "replacements": List[Dict]  # Lista de reemplazos aplicados
            }
        """
        if not text:
            return {
                "original": text,
                "normalized": text,
                "replacements": []
            }
        
        rules_to_apply = rules if rules is not None else self._replacement_rules
        normalized = text
        replacements_applied = []
        
        for rule in rules_to_apply:
            pattern = rule["pattern"]
            replacement = rule["replacement"]
            flags = rule.get("flags", 0)
            
            try:
                # Compilar el patrón
                compiled_pattern = re.compile(pattern, flags)
                
                # Buscar todas las coincidencias antes de reemplazar
                matches = list(compiled_pattern.finditer(normalized))
                
                if matches:
                    # Aplicar el reemplazo
                    new_text = compiled_pattern.sub(replacement, normalized)
                    
                    # Registrar los reemplazos
                    for match in matches:
                        replacements_applied.append({
                            "pattern": pattern,
                            "replacement": replacement,
                            "matched": match.group(0),
                            "position": match.start(),
                            "description": rule.get("description")
                        })
                    
                    normalized = new_text
            except re.error as e:
                # Si el patrón es inválido, continuar con la siguiente regla
                replacements_applied.append({
                    "pattern": pattern,
                    "replacement": replacement,
                    "error": f"Invalid regex pattern: {str(e)}"
                })
                continue
        
        return {
            "original": text,
            "normalized": normalized,
            "replacements": replacements_applied
        }
    
    def normalize_batch(
        self,
        texts: List[str],
        rules: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Normaliza múltiples textos aplicando las reglas de reemplazo
        
        Args:
            texts: Lista de textos a normalizar
            rules: Lista opcional de reglas a aplicar
        
        Returns:
            Lista de resultados de normalización
        """
        return [self.normalize_text(text, rules) for text in texts]

