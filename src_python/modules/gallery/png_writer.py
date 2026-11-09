"""
Servicio para escribir metadatos en archivos PNG
Actualiza los chunks de texto (tEXt, zTXt, iTXt) en archivos PNG
"""

import zlib
import json
import struct
from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class PNGMetadataWriter:
    """Clase para escribir metadatos en archivos PNG"""
    
    PNG_SIGNATURE = bytes([137, 80, 78, 71, 13, 10, 26, 10])
    
    def update_png_metadata(
        self,
        file_path: Path,
        prompt_json: Optional[Dict] = None,
        workflow_json: Optional[Dict] = None,
        parameters: Optional[str] = None
    ) -> bool:
        """
        Actualiza los metadatos de un archivo PNG
        
        Args:
            file_path: Ruta del archivo PNG
            prompt_json: JSON del prompt (ComfyUI) - se actualizará el chunk 'prompt'
            workflow_json: JSON del workflow (ComfyUI) - se actualizará el chunk 'workflow'
            parameters: Texto de parameters (SD WebUI) - se actualizará el chunk 'parameters'
        
        Returns:
            True si se actualizó correctamente, False en caso contrario
        """
        try:
            # Leer el archivo completo
            with open(file_path, 'rb') as f:
                buffer = f.read()
            
            # Verificar firma PNG
            if len(buffer) < 8 or buffer[:8] != self.PNG_SIGNATURE:
                logger.error(f"El archivo {file_path} no es un PNG válido")
                return False
            
            # Reconstruir el archivo PNG preservando todos los chunks excepto los que actualizamos
            new_buffer = bytearray()
            new_buffer.extend(self.PNG_SIGNATURE)
            
            # Diccionario con los chunks a actualizar
            chunks_to_update = {}
            if prompt_json is not None:
                chunks_to_update['prompt'] = json.dumps(prompt_json)
            if workflow_json is not None:
                chunks_to_update['workflow'] = json.dumps(workflow_json)
            if parameters is not None:
                chunks_to_update['parameters'] = parameters
            
            if not chunks_to_update:
                logger.warning(f"No hay metadatos para actualizar en {file_path}")
                return False
            
            # Procesar todos los chunks
            offset = 8  # Saltar firma PNG
            chunks_updated = set()
            
            while offset + 8 <= len(buffer):
                # Leer longitud
                chunk_length = int.from_bytes(buffer[offset:offset+4], byteorder='big')
                offset += 4
                
                # Leer tipo
                chunk_type = buffer[offset:offset+4]
                offset += 4
                
                # Leer datos
                chunk_data = buffer[offset:offset+chunk_length]
                offset += chunk_length
                
                # Leer CRC
                chunk_crc = buffer[offset:offset+4]
                offset += 4
                
                # Verificar si es un chunk de texto que necesitamos actualizar
                if chunk_type in (b'tEXt', b'zTXt', b'iTXt'):
                    try:
                        # Extraer la clave
                        null_pos = chunk_data.find(0)
                        if null_pos >= 0:
                            chunk_key = chunk_data[:null_pos].decode('utf-8', errors='ignore')
                            
                            # Si es un chunk que necesitamos actualizar, crear uno nuevo
                            if chunk_key in chunks_to_update:
                                new_chunk = self._create_text_chunk(chunk_key, chunks_to_update[chunk_key])
                                new_buffer.extend(new_chunk)
                                chunks_updated.add(chunk_key)
                                continue
                    except Exception:
                        pass
                
                # Si no es un chunk que necesitamos actualizar, o si es IEND, copiarlo tal cual
                if chunk_type == b'IEND':
                    # Copiar IEND y terminar
                    new_buffer.extend(struct.pack('>I', chunk_length))
                    new_buffer.extend(chunk_type)
                    new_buffer.extend(chunk_data)
                    new_buffer.extend(chunk_crc)
                    break
                else:
                    # Copiar chunk tal cual
                    new_buffer.extend(struct.pack('>I', chunk_length))
                    new_buffer.extend(chunk_type)
                    new_buffer.extend(chunk_data)
                    new_buffer.extend(chunk_crc)
            
            # Si hay chunks que no existían, agregarlos antes del IEND
            for key, value in chunks_to_update.items():
                if key not in chunks_updated:
                    # Buscar IEND y insertar antes
                    iend_pos = new_buffer.find(b'IEND', 8)
                    if iend_pos > 0:
                        # Insertar antes del IEND (4 bytes antes para la longitud)
                        new_chunk = self._create_text_chunk(key, value)
                        new_buffer[iend_pos-4:iend_pos-4] = new_chunk
            
            # Guardar el archivo actualizado (hacer backup primero)
            backup_path = file_path.with_suffix(file_path.suffix + '.bak')
            try:
                import shutil
                shutil.copy2(file_path, backup_path)
            except Exception as e:
                logger.warning(f"No se pudo crear backup: {e}")
            
            with open(file_path, 'wb') as f:
                f.write(new_buffer)
            
            logger.info(f"Metadatos actualizados en {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error actualizando metadatos PNG en {file_path}: {e}", exc_info=True)
            return False
    
    def _create_text_chunk(self, key: str, value: str) -> bytes:
        """
        Crea un chunk de texto (tEXt) para PNG
        
        Args:
            key: Clave del chunk (ej: 'prompt', 'workflow', 'parameters')
            value: Valor del chunk (texto o JSON stringificado)
        
        Returns:
            Bytes del chunk completo (length + type + data + crc)
        """
        # Preparar el nuevo chunk
        key_bytes = key.encode('utf-8')
        value_bytes = value.encode('utf-8')
        
        # Crear chunk tEXt: [length(4)] [type(4)] [key + null(1) + value] [crc(4)]
        chunk_data = key_bytes + b'\x00' + value_bytes
        chunk_length = len(chunk_data)
        chunk_type = b'tEXt'
        
        # Calcular CRC: type + data
        crc_data = chunk_type + chunk_data
        crc = zlib.crc32(crc_data) & 0xffffffff
        
        # Crear el chunk completo
        new_chunk = struct.pack('>I', chunk_length) + chunk_type + chunk_data + struct.pack('>I', crc)
        
        return new_chunk
    
    def _find_text_chunk(self, buffer: bytes, key: str) -> Optional[Dict]:
        """
        Busca un chunk de texto específico en el buffer
        
        Returns:
            Dict con 'start' y 'end' si se encuentra, None si no
        """
        offset = 8  # Saltar firma PNG
        
        while offset + 8 <= len(buffer):
            # Leer longitud
            if offset + 4 > len(buffer):
                break
            chunk_length = int.from_bytes(buffer[offset:offset+4], byteorder='big')
            offset += 4
            
            # Leer tipo
            if offset + 4 > len(buffer):
                break
            chunk_type = buffer[offset:offset+4].decode('latin-1')
            offset += 4
            
            # Verificar espacio
            if offset + chunk_length + 4 > len(buffer):
                break
            
            chunk_start = offset - 8  # Inicio del chunk (incluye length y type)
            
            # Leer datos
            chunk_data = buffer[offset:offset+chunk_length]
            offset += chunk_length
            
            # Saltar CRC
            crc_pos = offset
            offset += 4
            
            chunk_end = offset  # Fin del chunk (incluye CRC)
            
            # Verificar si es un chunk de texto que nos interesa
            if chunk_type in ('tEXt', 'zTXt', 'iTXt'):
                try:
                    # Extraer la clave
                    if chunk_type == 'tEXt':
                        null_pos = chunk_data.find(0)
                        if null_pos >= 0:
                            chunk_key = chunk_data[:null_pos].decode('utf-8', errors='ignore')
                            if chunk_key == key:
                                return {'start': chunk_start, 'end': chunk_end, 'type': chunk_type}
                    elif chunk_type == 'zTXt':
                        null_pos = chunk_data.find(0)
                        if null_pos >= 0:
                            chunk_key = chunk_data[:null_pos].decode('utf-8', errors='ignore')
                            if chunk_key == key:
                                return {'start': chunk_start, 'end': chunk_end, 'type': chunk_type}
                    elif chunk_type == 'iTXt':
                        null_pos = chunk_data.find(0)
                        if null_pos >= 0:
                            chunk_key = chunk_data[:null_pos].decode('utf-8', errors='ignore')
                            if chunk_key == key:
                                return {'start': chunk_start, 'end': chunk_end, 'type': chunk_type}
                except Exception:
                    continue
        
        return None
    
    def _find_iend_chunk(self, buffer: bytes) -> Optional[int]:
        """Encuentra la posición del chunk IEND"""
        offset = 8
        while offset + 8 <= len(buffer):
            chunk_length = int.from_bytes(buffer[offset:offset+4], byteorder='big')
            offset += 4
            chunk_type = buffer[offset:offset+4]
            offset += 4
            
            if chunk_type == b'IEND':
                return offset - 8  # Retornar inicio del chunk IEND
            
            offset += chunk_length + 4  # Saltar datos y CRC
        
        return None
    
    def read_guid(self, file_path: Path) -> Optional[str]:
        """
        Lee el GUID almacenado en los metadatos del PNG
        
        Args:
            file_path: Ruta del archivo PNG
            
        Returns:
            GUID como string si existe, None si no se encuentra
        """
        try:
            with open(file_path, 'rb') as f:
                buffer = f.read()
            
            # Verificar firma PNG
            if len(buffer) < 8 or buffer[:8] != self.PNG_SIGNATURE:
                logger.debug(f"El archivo {file_path} no es un PNG válido")
                return None
            
            # Buscar chunk con clave 'ai_suite_guid'
            offset = 8  # Saltar firma PNG
            
            while offset + 8 <= len(buffer):
                # Leer longitud
                chunk_length = int.from_bytes(buffer[offset:offset+4], byteorder='big')
                offset += 4
                
                # Leer tipo
                chunk_type = buffer[offset:offset+4]
                offset += 4
                
                # Leer datos
                chunk_data = buffer[offset:offset+chunk_length]
                offset += chunk_length
                
                # Saltar CRC
                offset += 4
                
                # Verificar si es un chunk de texto
                if chunk_type in (b'tEXt', b'zTXt', b'iTXt'):
                    try:
                        # Extraer la clave
                        null_pos = chunk_data.find(0)
                        if null_pos >= 0:
                            chunk_key = chunk_data[:null_pos].decode('utf-8', errors='ignore')
                            
                            # Si es el chunk de GUID, extraer el valor
                            if chunk_key == 'ai_suite_guid':
                                if chunk_type == b'tEXt':
                                    # tEXt: key\0value
                                    guid_value = chunk_data[null_pos+1:].decode('utf-8', errors='ignore')
                                    return guid_value.strip()
                                elif chunk_type == b'zTXt':
                                    # zTXt: key\0method\0compressed_data
                                    if len(chunk_data) >= null_pos + 2:
                                        method = chunk_data[null_pos + 1]
                                        if method == 0:  # zlib
                                            compressed_data = chunk_data[null_pos + 2:]
                                            guid_value = zlib.decompress(compressed_data).decode('utf-8', errors='ignore')
                                            return guid_value.strip()
                                elif chunk_type == b'iTXt':
                                    # iTXt es más complejo, por ahora solo soportamos tEXt
                                    pass
                    except Exception as e:
                        logger.debug(f"Error leyendo chunk de GUID: {e}")
                        continue
                
                # Si encontramos IEND, terminar
                if chunk_type == b'IEND':
                    break
            
            return None
            
        except Exception as e:
            logger.error(f"Error leyendo GUID de {file_path}: {e}", exc_info=True)
            return None
    
    def write_guid(self, file_path: Path, guid: str) -> bool:
        """
        Escribe el GUID en los metadatos del PNG (chunk tEXt con clave 'ai_suite_guid')
        
        Args:
            file_path: Ruta del archivo PNG
            guid: GUID a escribir (string UUID)
            
        Returns:
            True si se escribió correctamente, False en caso contrario
        """
        try:
            # Verificar que el archivo existe y es accesible
            if not file_path.exists():
                logger.error(f"[GUID] El archivo no existe: {file_path}")
                return False
            
            if not file_path.is_file():
                logger.error(f"[GUID] La ruta no es un archivo: {file_path}")
                return False
            
            # Verificar permisos de escritura
            if not file_path.parent.exists():
                logger.error(f"[GUID] El directorio padre no existe: {file_path.parent}")
                return False
            # Usar el método existente update_png_metadata pero con un enfoque más directo
            # Leer el archivo completo
            with open(file_path, 'rb') as f:
                buffer = f.read()
            
            # Verificar firma PNG
            if len(buffer) < 8 or buffer[:8] != self.PNG_SIGNATURE:
                logger.error(f"El archivo {file_path} no es un PNG válido")
                return False
            
            # Reconstruir el archivo PNG
            new_buffer = bytearray()
            new_buffer.extend(self.PNG_SIGNATURE)
            
            # Procesar todos los chunks
            offset = 8  # Saltar firma PNG
            guid_chunk_added = False
            
            while offset + 8 <= len(buffer):
                # Leer longitud
                chunk_length = int.from_bytes(buffer[offset:offset+4], byteorder='big')
                offset += 4
                
                # Leer tipo
                chunk_type = buffer[offset:offset+4]
                offset += 4
                
                # Leer datos
                chunk_data = buffer[offset:offset+chunk_length]
                offset += chunk_length
                
                # Leer CRC
                chunk_crc = buffer[offset:offset+4]
                offset += 4
                
                # Si encontramos IEND, insertar el GUID antes
                if chunk_type == b'IEND' and not guid_chunk_added:
                    # Crear chunk de GUID
                    guid_chunk = self._create_text_chunk('ai_suite_guid', guid)
                    new_buffer.extend(guid_chunk)
                    guid_chunk_added = True
                
                # Verificar si es el chunk de GUID existente (para reemplazarlo)
                if chunk_type in (b'tEXt', b'zTXt', b'iTXt'):
                    try:
                        null_pos = chunk_data.find(0)
                        if null_pos >= 0:
                            chunk_key = chunk_data[:null_pos].decode('utf-8', errors='ignore')
                            if chunk_key == 'ai_suite_guid':
                                # Reemplazar con el nuevo GUID
                                guid_chunk = self._create_text_chunk('ai_suite_guid', guid)
                                new_buffer.extend(guid_chunk)
                                guid_chunk_added = True
                                continue
                    except Exception:
                        pass
                
                # Copiar chunk tal cual
                new_buffer.extend(struct.pack('>I', chunk_length))
                new_buffer.extend(chunk_type)
                new_buffer.extend(chunk_data)
                new_buffer.extend(chunk_crc)
                
                # Si encontramos IEND, terminar
                if chunk_type == b'IEND':
                    break
            
            # Si no se agregó el GUID, agregarlo antes del IEND
            if not guid_chunk_added:
                # Buscar IEND y insertar antes
                iend_pos = new_buffer.find(b'IEND', 8)
                if iend_pos > 0:
                    guid_chunk = self._create_text_chunk('ai_suite_guid', guid)
                    # Insertar antes del IEND
                    # Necesitamos insertar en la posición correcta (antes de los 4 bytes de longitud del IEND)
                    new_buffer = new_buffer[:iend_pos-4] + guid_chunk + new_buffer[iend_pos-4:]
            
            # Guardar el archivo actualizado (hacer backup primero solo si no existe)
            backup_path = file_path.with_suffix(file_path.suffix + '.bak')
            backup_created = False
            try:
                import shutil
                # Solo crear backup si no existe ya
                if not backup_path.exists():
                    shutil.copy2(file_path, backup_path)
                    backup_created = True
            except Exception as e:
                logger.warning(f"No se pudo crear backup: {e}")
            
            try:
                with open(file_path, 'wb') as f:
                    f.write(new_buffer)
                
                # Verificar que el archivo se escribió correctamente
                if not file_path.exists() or file_path.stat().st_size == 0:
                    logger.error(f"Error: El archivo {file_path} no se escribió correctamente")
                    # Restaurar desde backup si existe
                    if backup_path.exists():
                        try:
                            shutil.copy2(backup_path, file_path)
                            logger.info(f"Archivo restaurado desde backup: {file_path}")
                        except Exception as restore_error:
                            logger.error(f"Error restaurando desde backup: {restore_error}")
                    return False
                
                # Si todo salió bien y creamos un backup nuevo, eliminar backups antiguos
                # (mantener solo el más reciente)
                if backup_created:
                    logger.debug(f"GUID escrito en {file_path}: {guid}")
                    return True
                else:
                    # Si el backup ya existía, verificar que la escritura fue exitosa
                    logger.debug(f"GUID escrito en {file_path}: {guid} (backup ya existía)")
                    return True
                    
            except Exception as write_error:
                logger.error(f"Error escribiendo archivo {file_path}: {write_error}", exc_info=True)
                # Restaurar desde backup si existe
                if backup_path.exists():
                    try:
                        shutil.copy2(backup_path, file_path)
                        logger.info(f"Archivo restaurado desde backup después de error: {file_path}")
                    except Exception as restore_error:
                        logger.error(f"Error restaurando desde backup: {restore_error}")
                return False
            
        except Exception as e:
            logger.error(f"Error escribiendo GUID en {file_path}: {e}", exc_info=True)
            return False

