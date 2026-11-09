"""
Event Bus - Para comunicación entre módulos
Paso 1.3 - Event Bus Básico (sin async)
Paso 9.1 - Event Bus Completo (async)
Permite desacoplamiento entre módulos mediante eventos
"""

from typing import Callable, Dict, List, Any, Optional, Awaitable, Union
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import asyncio


class EventType(Enum):
    """Tipos de eventos del sistema"""
    # Gallery events
    IMAGE_SCANNED = "image_scanned"
    FOLDER_SCANNED = "folder_scanned"
    THUMBNAIL_GENERATED = "thumbnail_generated"
    
    # Extractor events
    ANALYSIS_COMPLETED = "analysis_completed"
    TRANSLATION_COMPLETED = "translation_completed"
    
    # CivitAI events
    DOWNLOAD_STARTED = "download_started"
    DOWNLOAD_PROGRESS = "download_progress"
    DOWNLOAD_COMPLETED = "download_completed"
    
    # Metadata events
    METADATA_UPDATED = "metadata_updated"


@dataclass
class Event:
    """Representa un evento del sistema"""
    event_type: EventType
    payload: Dict[str, Any]
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


# Tipo para handlers async y sync
EventHandler = Union[
    Callable[[Event], None],  # Handler síncrono
    Callable[[Event], Awaitable[None]]  # Handler async
]


class EventBus:
    """
    Bus de eventos para comunicación entre módulos
    Patrón Observer/Publisher-Subscriber
    Soporta handlers síncronos y asíncronos
    """
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[EventHandler]] = {}
    
    def subscribe(self, event_type: EventType, handler: EventHandler):
        """
        Suscribe un handler a un tipo de evento
        
        Args:
            event_type: Tipo de evento al que suscribirse
            handler: Función (sync o async) que se ejecutará cuando se publique el evento
                    Debe aceptar un parámetro Event
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
    
    def unsubscribe(self, event_type: EventType, handler: EventHandler):
        """
        Desuscribe un handler de un tipo de evento
        
        Args:
            event_type: Tipo de evento
            handler: Handler a desuscribir
        """
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass
    
    def publish(self, event: Event):
        """
        Publica un evento a todos los suscriptores (síncrono)
        Los handlers async se ejecutan en el event loop actual si existe
        
        Args:
            event: Evento a publicar
        """
        handlers = self._subscribers.get(event.event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    # Handler async - intentar ejecutar en el loop actual
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Loop ya está corriendo, crear tarea
                            asyncio.create_task(handler(event))
                        else:
                            # Loop no está corriendo, ejecutar directamente
                            loop.run_until_complete(handler(event))
                    except RuntimeError:
                        # No hay loop, ejecutar en uno nuevo
                        asyncio.run(handler(event))
                else:
                    # Handler síncrono
                    handler(event)
            except Exception as e:
                # Log error pero no interrumpir otros handlers
                print(f"Error en handler de evento {event.event_type}: {e}")
    
    async def publish_async(self, event: Event):
        """
        Publica un evento a todos los suscriptores (async)
        Ejecuta todos los handlers de forma asíncrona
        
        Args:
            event: Evento a publicar
        """
        handlers = self._subscribers.get(event.event_type, [])
        tasks = []
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    # Handler async
                    tasks.append(asyncio.create_task(handler(event)))
                else:
                    # Handler síncrono - ejecutar en executor
                    loop = asyncio.get_event_loop()
                    tasks.append(loop.run_in_executor(None, handler, event))
            except Exception as e:
                # Log error pero no interrumpir otros handlers
                print(f"Error al preparar handler de evento {event.event_type}: {e}")
        
        # Esperar a que todos los handlers terminen
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Log errores si los hay
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"Error en handler {i} de evento {event.event_type}: {result}")
    
    def get_subscriber_count(self, event_type: EventType) -> int:
        """Retorna el número de suscriptores para un tipo de evento"""
        return len(self._subscribers.get(event_type, []))
    
    def clear_subscribers(self, event_type: Optional[EventType] = None):
        """
        Limpia suscriptores
        
        Args:
            event_type: Si se especifica, limpia solo ese tipo. Si es None, limpia todos.
        """
        if event_type:
            self._subscribers.pop(event_type, None)
        else:
            self._subscribers.clear()


# Instancia global del event bus
event_bus = EventBus()

