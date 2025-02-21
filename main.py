from fastapi import FastAPI
import uvicorn
from contextlib import asynccontextmanager
import aiofiles
import json

# Custom imports
from app.utils.config import settings
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.update import router as update_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the configuration file at startup
    async with aiofiles.open("app/config/custom_config.json", "r") as file:
        contents = await file.read()
        app.state.config = json.loads(contents)
    yield
    # Save the configuration file at shutdown
    async with aiofiles.open("app/config/custom_config.json", "w") as file:
        await file.write(json.dumps(app.state.config, indent=4))

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(update_router)

@app.get("/")
def read_root():
    return {"message": "Welcome to " + settings.APP_NAME}

if __name__ == "__main__":
    uvicorn.run("main:app", host="localhost", port=8000, reload=True)
