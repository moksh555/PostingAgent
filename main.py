import logging

from fastapi import FastAPI, Request, status  # type: ignore
from fastapi.exceptions import RequestValidationError  # type: ignore
from fastapi.responses import JSONResponse  # type: ignore

from app.api.router import router as mainRouter
from app.errorsHandler.errors import AppError


APP_VERSION = "1.0.0:v1"

app = FastAPI(
    title="Marketing Agent API",
    version=APP_VERSION,
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
