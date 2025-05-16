import logging
from app.api import api_router
from app.core.env_settings import env
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set to DEBUG for more verbose logging

app = FastAPI(title=env.APP_NAME, description="Valorence Control System",)
app.add_event_handler("startup", lambda: logger.info("Starting up..."))
app.add_event_handler("shutdown", lambda: logger.info("Shutting down..."))


# Add middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handler
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error"},
    )

# Register API routers
app.include_router(api_router, prefix="/api")

# If running as a script
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        ssl_keyfile=env.SSL_KEY_FILE,
        ssl_certfile=env.SSL_CERT_FILE,
    )