import logging

from fastapi import FastAPI, Request, status  # type: ignore
from fastapi.exceptions import RequestValidationError  # type: ignore
from fastapi.responses import JSONResponse  # type: ignore

from app.api.router import router as mainRouter

logger = logging.getLogger(__name__)

APP_VERSION = "1.0.0:v1"

app = FastAPI(
    title="Marketing Agent API",
    version=APP_VERSION,
)


@app.exception_handler(RequestValidationError)
async def on_request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return a consistent envelope for 422 validation failures."""
    logger.info("Request validation failed on %s: %s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "code": "validation_error",
            "message": "Request body failed validation",
            "errors": exc.errors(),
        },
    )


app.include_router(mainRouter)
