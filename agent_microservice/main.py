import logging
from fastapi.middleware.cors import CORSMiddleware #type: ignore
from fastapi import FastAPI, Request  # type: ignore
from fastapi.responses import JSONResponse  # type: ignore

from app.api.router import router as mainRouter
from app.errorsHandler.errors import AppError


APP_VERSION = "1.0.0:v1"

app = FastAPI(
    title="Agent Microservice - Marketing Agent",
    version=APP_VERSION,
)

origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "code": exc.code,
            "message": exc.message,
        }
    )


app.include_router(mainRouter)
