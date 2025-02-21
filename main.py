from fastapi import FastAPI
import uvicorn
from app.core.config import settings
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router

# You can import other routers (e.g., admin, user) as they get implemented

app = FastAPI(title=settings.APP_NAME)

# Include the authentication routes
app.include_router(auth_router)
app.include_router(admin_router)

@app.get("/")
def read_root():
    return {"message": "Welcome to " + settings.APP_NAME}

if __name__ == "__main__":
    uvicorn.run("main:app", host="localhost", port=8000, reload=True)
