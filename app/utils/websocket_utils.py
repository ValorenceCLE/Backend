"""
Shared WebSocket utilities for handling connections and managing resources
across all WebSocket endpoints in the application.
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable, Awaitable
from fastapi import WebSocket, HTTPException, status
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class WebSocketManager:
    """
    Central WebSocket connection manager that handles:
    - Connection registration and tracking
    - Resource cleanup
    - Safe message sending with error handling
    - Graceful connection termination
    """
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.shared_resources: Dict[str, Any] = {}
    
    def register_connection(self, key: str, websocket: WebSocket) -> None:
        """Register an active WebSocket connection under a specific key"""
        if key not in self.active_connections:
            self.active_connections[key] = []
        self.active_connections[key].append(websocket)
        logger.debug(f"Registered connection for {key}, total: {len(self.active_connections[key])}")
    
    def unregister_connection(self, key: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from tracking"""
        if key in self.active_connections:
            try:
                self.active_connections[key].remove(websocket)
                logger.debug(f"Unregistered connection for {key}, remaining: {len(self.active_connections[key])}")
            except ValueError:
                pass  # Already removed
    
    def store_resource(self, key: str, resource: Any) -> None:
        """Store a shared resource for reuse"""
        self.shared_resources[key] = resource
    
    def get_resource(self, key: str) -> Optional[Any]:
        """Retrieve a shared resource by key"""
        return self.shared_resources.get(key)
    
    def broadcast_to_group(self, key: str, message: Any) -> None:
        """Send a message to all connections in a group"""
        if key in self.active_connections:
            # Use asyncio.gather to send messages in parallel
            asyncio.create_task(
                asyncio.gather(
                    *[self.send_json(websocket, message) for websocket in self.active_connections[key]],
                    return_exceptions=True
                )
            )

async def safe_send_json(websocket: WebSocket, data: Any) -> bool:
    """Safely send JSON data with proper error handling for closed connections"""
    try:
        await websocket.send_json(data)
        return True
    except RuntimeError as e:
        if "close message has been sent" in str(e):
            # Connection is already closed, no need for further action
            return False
        raise
    except Exception as e:
        logger.error(f"Error sending JSON data: {e}")
        return False

async def safe_send_text(websocket: WebSocket, text: str) -> bool:
    """Safely send text with proper error handling for closed connections"""
    try:
        await websocket.send_text(text)
        return True
    except RuntimeError as e:
        if "close message has been sent" in str(e):
            # Connection is already closed, no need for further action
            return False
        raise
    except Exception as e:
        logger.error(f"Error sending text message: {e}")
        return False

async def safe_close(websocket: WebSocket, code: int = status.WS_1000_NORMAL_CLOSURE) -> bool:
    """Safely close a WebSocket connection with error handling"""
    try:
        await websocket.close(code=code)
        return True
    except Exception as e:
        logger.debug(f"Error closing WebSocket (likely already closed): {e}")
        return False

@asynccontextmanager
async def websocket_connection(
    websocket: WebSocket,
    manager: WebSocketManager,
    connection_id: str,
    on_connect: Optional[Callable[[WebSocket], Awaitable[bool]]] = None,
    on_disconnect: Optional[Callable[[WebSocket], Awaitable[None]]] = None
):
    """
    Context manager for WebSocket connections that handles:
    - Connection acceptance
    - Registration with the connection manager
    - Custom connection initialization via on_connect callback
    - Automatic cleanup and unregistration on exit
    - Custom cleanup via on_disconnect callback
    
    Usage:
        async with websocket_connection(websocket, manager, "connection_id") as connected:
            if not connected:
                return  # Connection failed
            
            # Normal WebSocket communication
    """
    is_connected = False
    try:
        # Accept the WebSocket connection
        await websocket.accept()
        is_connected = True
        
        # Run custom connection initialization if provided
        if on_connect:
            if not await on_connect(websocket):
                await safe_close(websocket)
                yield False
                return
        
        # Register with the connection manager
        manager.register_connection(connection_id, websocket)
        
        # Yield control back to the caller with connection status
        yield True
        
    except Exception as e:
        logger.exception(f"Error establishing WebSocket connection: {e}")
        if is_connected:
            await safe_close(websocket)
        yield False
        
    finally:
        # Run custom disconnect handler if provided
        if is_connected and on_disconnect:
            await on_disconnect(websocket)
            
        # Ensure proper cleanup
        manager.unregister_connection(connection_id, websocket)
        logger.debug(f"WebSocket connection context for {connection_id} exited")

# Global WebSocket manager instance
ws_manager = WebSocketManager()