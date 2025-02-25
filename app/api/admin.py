from fastapi import Request, APIRouter, HTTPException, Depends
from app.utils.dependencies import require_role


router = APIRouter(prefix="/admin", tags=["Admin APi Configuration"])
    
@router.get("/", summary="Retrieve custom configuration")
async def get_custom_config(request: Request):
    try:
        return request.app.state.config
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading custom config file: {e}")
    
@router.get("/{config_section}", summary="Retrieve specific configuration section", dependencies=[Depends(require_role("admin"))])
async def get_config_section(request: Request, config_section: str):
    try:
        print(request.app.state.config[config_section])
        return request.app.state.config[config_section]
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Configuration section '{config_section}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading custom config file: {e}")
    
@router.post("/", summary="Update custom configuration")
async def update_custom_config(request: Request, new_config: dict):
    try:
        request.app.state.config = new_config
        print("New Config:", request.app.state.config)
        return {"message": "Configuration updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating custom config file: {e}")
    
@router.post("/{config_section}", summary="Update specific configuration section")
async def update_config_section(request: Request, config_section: str, new_config: dict):
    try:
        if config_section in request.app.state.config:
            request.app.state.config[config_section] = new_config
            return {"message": f"Configuration section '{config_section}' updated successfully"}
        else:
            raise HTTPException(status_code=404, detail=f"Configuration section '{config_section}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating custom config file: {e}")