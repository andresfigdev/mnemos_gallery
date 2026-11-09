"""
Servicio de extracción de metadatos de imágenes generadas con IA
Soporta: ComfyUI, Stable Diffusion WebUI

Basado en el proyecto comfy-gallery-v2
"""

import json
import zlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Intentar importar PIL/Pillow
try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    PILImage = None


@dataclass
class LoraInfo:
    """Información de un LoRA"""
    name: str
    strength: Optional[float] = None
    strength_model: Optional[float] = None


@dataclass
class ImageMetadata:
    """Metadatos extraídos de una imagen"""
    source: str  # 'none' | 'comfyui' | 'sd-webui'
    model: Optional[str] = None
    sampler: Optional[str] = None
    steps: Optional[int] = None
    cfg: Optional[float] = None
    denoise: Optional[float] = None
    seed: Optional[str] = None
    prompt_pos: Optional[str] = None
    prompt_neg: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    loras: Optional[List[LoraInfo]] = None
    prompt_json: Optional[Dict[str, Any]] = None  # JSON parseado de ComfyUI
    workflow_json: Optional[Dict[str, Any]] = None  # JSON parseado de ComfyUI
    raw_parameters: Optional[str] = None  # Parámetros crudos de SD WebUI
    warning: Optional[str] = None
    error_code: Optional[str] = None


class MetadataService:
    """Servicio para extraer metadatos de imágenes PNG"""
    
    # Firma PNG: 89 50 4E 47 0D 0A 1A 0A
    PNG_SIGNATURE = bytes([137, 80, 78, 71, 13, 10, 26, 10])
    
    def extract_metadata(self, file_path: Path) -> ImageMetadata:
        """
        Extrae metadatos de una imagen PNG
        
        Args:
            file_path: Path del archivo PNG
            
        Returns:
            ImageMetadata con los metadatos extraídos
        """
        # Solo procesar archivos PNG
        if not file_path.suffix.lower() == '.png':
            return ImageMetadata(source='none')
        
        # Leer archivo
        try:
            with open(file_path, 'rb') as f:
                buffer = f.read()
        except Exception as e:
            return ImageMetadata(
                source='none',
                warning=f'No se pudo leer el archivo: {str(e)}',
                error_code='READ_FAIL'
            )
        
        # Extraer chunks de texto
        try:
            text_pairs = self._extract_png_text_chunks(buffer)
        except Exception as e:
            return ImageMetadata(
                source='none',
                warning=f'Error al parsear chunks PNG: {str(e)}',
                error_code='PNG_PARSE'
            )
        
        parameters = text_pairs.get('parameters', '')
        prompt_json_str = text_pairs.get('prompt', '')
        workflow_json_str = text_pairs.get('workflow', '')
        
        has_prompt_json = bool(prompt_json_str)
        has_workflow_json = bool(workflow_json_str)
        
        # Prioridad 1: ComfyUI (si tiene prompt.json o workflow.json)
        if has_prompt_json or has_workflow_json:
            return self._extract_comfyui_metadata(
                prompt_json_str,
                workflow_json_str,
                parameters
            )
        
        # Prioridad 2: SD WebUI (si tiene parameters)
        if parameters:
            return self._extract_sd_webui_metadata(parameters)
        
        # Sin metadatos
        return ImageMetadata(
            source='none',
            prompt_json=None,
            workflow_json=None
        )
    
    def _extract_png_text_chunks(self, buffer: bytes) -> Dict[str, str]:
        """
        Extrae chunks de texto de un archivo PNG (tEXt, zTXt, iTXt)
        Busca específicamente: parameters, prompt, workflow
        """
        # Verificar firma PNG
        if len(buffer) < 8 or buffer[:8] != self.PNG_SIGNATURE:
            return {}
        
        text_pairs: Dict[str, str] = {}
        offset = 8
        
        while offset + 8 <= len(buffer):
            # Leer longitud del chunk (4 bytes big-endian)
            if offset + 4 > len(buffer):
                break
            chunk_length = int.from_bytes(buffer[offset:offset+4], byteorder='big')
            offset += 4
            
            # Leer tipo de chunk (4 bytes)
            if offset + 4 > len(buffer):
                break
            chunk_type = buffer[offset:offset+4].decode('latin-1')
            offset += 4
            
            # Verificar que hay espacio para datos + CRC
            if offset + chunk_length + 4 > len(buffer):
                break
            
            # Leer datos del chunk
            chunk_data = buffer[offset:offset+chunk_length]
            offset += chunk_length
            
            # Saltar CRC (4 bytes)
            offset += 4
            
            # Procesar según el tipo de chunk
            if chunk_type == 'tEXt':
                # Chunk tEXt (texto sin comprimir)
                null_pos = chunk_data.find(0)
                if null_pos >= 0:
                    key = chunk_data[:null_pos].decode('utf-8', errors='ignore')
                    value = chunk_data[null_pos+1:].decode('utf-8', errors='ignore')
                    text_pairs[key] = value
            
            elif chunk_type == 'zTXt':
                # Chunk zTXt (texto comprimido con zlib)
                null_pos = chunk_data.find(0)
                if null_pos >= 0 and len(chunk_data) >= null_pos + 2:
                    key = chunk_data[:null_pos].decode('utf-8', errors='ignore')
                    method = chunk_data[null_pos + 1]
                    if method == 0:  # zlib
                        try:
                            compressed_data = chunk_data[null_pos + 2:]
                            decompressed = zlib.decompress(compressed_data)
                            text_pairs[key] = decompressed.decode('utf-8', errors='ignore')
                        except Exception:
                            pass  # Ignorar errores de descompresión
            
            elif chunk_type == 'iTXt':
                # Chunk iTXt (texto internacional, puede estar comprimido)
                try:
                    # Leer key (hasta null)
                    null_pos = chunk_data.find(0)
                    if null_pos < 0:
                        continue
                    key = chunk_data[:null_pos].decode('utf-8', errors='ignore')
                    
                    # Leer compression flag y method
                    if len(chunk_data) < null_pos + 2:
                        continue
                    comp_flag = chunk_data[null_pos + 1]
                    comp_method = chunk_data[null_pos + 2]
                    
                    # Saltar lang y translated (hasta encontrar el siguiente null o fin)
                    rest_start = null_pos + 3
                    # Buscar el siguiente null (lang)
                    lang_end = chunk_data.find(0, rest_start)
                    if lang_end < 0:
                        continue
                    # Buscar el siguiente null (translated)
                    translated_end = chunk_data.find(0, lang_end + 1)
                    if translated_end < 0:
                        continue
                    
                    rest_data = chunk_data[translated_end + 1:]
                    
                    if comp_flag == 1 and comp_method == 0:  # zlib
                        try:
                            decompressed = zlib.decompress(rest_data)
                            text_pairs[key] = decompressed.decode('utf-8', errors='ignore')
                        except Exception:
                            pass
                    else:
                        text_pairs[key] = rest_data.decode('utf-8', errors='ignore')
                except Exception:
                    pass  # Ignorar errores
            
            elif chunk_type == 'IEND':
                # Fin del archivo
                break
            
            # Early exit si ya tenemos todos los campos importantes
            if 'parameters' in text_pairs and 'prompt' in text_pairs and 'workflow' in text_pairs:
                break
        
        return text_pairs
    
    def _extract_comfyui_metadata(
        self,
        prompt_json_str: str,
        workflow_json_str: str,
        parameters: str
    ) -> ImageMetadata:
        """
        Extrae metadatos del formato JSON de ComfyUI
        """
        metadata = ImageMetadata(source='comfyui')
        
        # Parsear prompt.json
        prompt_json = None
        if prompt_json_str:
            try:
                prompt_json = json.loads(prompt_json_str)
                metadata.prompt_json = prompt_json
                logger.debug(f"Prompt JSON parseado correctamente: {len(prompt_json)} nodos")
            except json.JSONDecodeError as e:
                logger.warning(f"Error parseando prompt.json: {str(e)}")
                # Intentar guardar como string si no se puede parsear
                try:
                    metadata.prompt_json = {"raw": prompt_json_str}
                except:
                    pass
        
        # Parsear workflow.json
        workflow_json = None
        if workflow_json_str:
            try:
                workflow_json = json.loads(workflow_json_str)
                metadata.workflow_json = workflow_json
                logger.debug(f"Workflow JSON parseado correctamente")
            except json.JSONDecodeError as e:
                logger.warning(f"Error parseando workflow.json: {str(e)}")
                # Intentar guardar como string si no se puede parsear
                try:
                    metadata.workflow_json = {"raw": workflow_json_str}
                except:
                    pass
        
        # Extraer campos del prompt.json
        if prompt_json:
            nodes = list(prompt_json.values()) if isinstance(prompt_json, dict) else []
            
            # Buscar nodo Sampler
            sampler_node = None
            for node in nodes:
                if isinstance(node, dict) and 'class_type' in node:
                    class_type = node.get('class_type', '').lower()
                    if 'sampler' in class_type:
                        sampler_node = node
                        break
            
            if sampler_node:
                inputs = sampler_node.get('inputs', {})
                metadata.sampler = inputs.get('sampler_name')
                metadata.steps = inputs.get('steps')
                metadata.cfg = inputs.get('cfg')
                metadata.seed = str(inputs.get('seed', ''))
                metadata.denoise = inputs.get('denoise')
            
            # Buscar CheckpointLoader
            checkpoint_node = None
            for node in nodes:
                if isinstance(node, dict) and 'class_type' in node:
                    class_type = node.get('class_type', '')
                    if class_type in ('CheckpointLoaderSimple', 'CheckpointLoader'):
                        checkpoint_node = node
                        break
            
            if checkpoint_node:
                inputs = checkpoint_node.get('inputs', {})
                metadata.model = inputs.get('ckpt_name')
            
            # Buscar CLIPTextEncode (prompts)
            clip_nodes = [
                node for node in nodes
                if isinstance(node, dict) and node.get('class_type') == 'CLIPTextEncode'
            ]
            
            for clip_node in clip_nodes:
                inputs = clip_node.get('inputs', {})
                text = inputs.get('text', '')
                if text:
                    # Heurística: si contiene palabras negativas comunes, es negative
                    is_negative = any(word in text.lower() for word in [
                        'bad', 'ugly', 'worst', 'low quality', 'blurry', 'deformed'
                    ])
                    if is_negative and not metadata.prompt_neg:
                        metadata.prompt_neg = text
                    elif not metadata.prompt_pos:
                        metadata.prompt_pos = text
            
            # Buscar LoRA Loaders
            lora_nodes = [
                node for node in nodes
                if isinstance(node, dict) and node.get('class_type') in (
                    'LoraLoader', 'LoraLoaderModelOnly'
                )
            ]
            
            if lora_nodes:
                loras = []
                for lora_node in lora_nodes:
                    inputs = lora_node.get('inputs', {})
                    lora_name = inputs.get('lora_name')
                    if lora_name:
                        loras.append(LoraInfo(
                            name=lora_name,
                            strength=inputs.get('strength'),
                            strength_model=inputs.get('strength_model')
                        ))
                if loras:
                    metadata.loras = loras
        
        # Guardar raw_parameters si existe
        if parameters:
            metadata.raw_parameters = parameters
        
        return metadata
    
    def _extract_sd_webui_metadata(self, parameters: str) -> ImageMetadata:
        """
        Parsea el formato de metadatos de SD WebUI (texto plano)
        Formato: "Steps: 20, Sampler: Euler, CFG: 7, Seed: 123..."
        """
        metadata = ImageMetadata(source='sd-webui', raw_parameters=parameters)
        
        if not parameters:
            return metadata
        
        lines = parameters.split('\n')
        neg_idx = next((i for i, l in enumerate(lines) if l.strip().lower().startswith('negative prompt:')), -1)
        steps_idx = next((i for i, l in enumerate(lines) if l.strip().lower().startswith('steps:')), -1)
        
        # Extraer Negative Prompt
        if neg_idx >= 0:
            after_neg = lines[neg_idx].replace('Negative prompt:', '').replace('negative prompt:', '').strip()
            next_idx = steps_idx if steps_idx > neg_idx else len(lines)
            metadata.prompt_neg = '\n'.join([after_neg] + lines[neg_idx + 1:next_idx]).strip()
        
        # Extraer Positive Prompt
        if neg_idx >= 0:
            metadata.prompt_pos = '\n'.join(lines[:neg_idx]).strip()
        elif steps_idx >= 0:
            metadata.prompt_pos = '\n'.join(lines[:steps_idx]).strip()
        else:
            metadata.prompt_pos = parameters.strip()
        
        # Extraer parámetros (Steps, Sampler, CFG, etc.)
        params_line = next((l for l in lines if l.strip().lower().startswith('steps:')), None)
        if not params_line:
            return metadata
        
        parts = [p.strip() for p in params_line.split(',') if p.strip()]
        
        for part in parts:
            if ':' not in part:
                continue
            
            key, value = part.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            
            if key.startswith('steps'):
                try:
                    metadata.steps = int(value)
                except ValueError:
                    pass
            elif key.startswith('sampler'):
                metadata.sampler = value
            elif key.startswith('cfg'):
                try:
                    metadata.cfg = float(value)
                except ValueError:
                    pass
            elif key.startswith('seed'):
                metadata.seed = value
            elif key.startswith('size'):
                # Formato: "512x512"
                if 'x' in value:
                    try:
                        w, h = value.split('x')
                        metadata.width = int(w.strip())
                        metadata.height = int(h.strip())
                    except ValueError:
                        pass
            elif key.startswith('model'):
                metadata.model = value
            elif key.startswith('denois'):
                try:
                    metadata.denoise = float(value)
                except ValueError:
                    pass
        
        return metadata

