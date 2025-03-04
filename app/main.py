from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from contextlib import asynccontextmanager
import aiofiles
import json

# Custom imports
from utils.config import settings
from api.auth import router as auth_router
from api.admin import router as admin_router

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

# ✅ CORS MIDDLEWARE HERE (before router includes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Vue frontend (Vite default port)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail}
    )

app.include_router(auth_router)
app.include_router(admin_router)


@app.get("/")
def read_root():
    return {"message": "Welcome to " + settings.APP_NAME}

if __name__ == "__main__":
    uvicorn.run("main:app", host="localhost", port=8000, reload=True)
