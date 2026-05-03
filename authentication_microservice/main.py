from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status #type: ignore
from fastapi.exceptions import RequestValidationError #type: ignore
from fastapi.responses import JSONResponse #type: ignore
from app.api.router import router as mainRouter
from fastapi.middleware.cors import CORSMiddleware #type: ignore
from app.errorsHandler.baseError import AuthenticationError
from app.repository.postgreSql import PostgreSQLRepository
from configurations.config import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = PostgreSQLRepository(config.POSTGRES_DB_URI)
    await db.connect()
    app.state.db = db
    try:
        yield
    finally:
        await db.disconnect()


app = FastAPI(
    title="Authentication Microservice - User Authentication",
    version="1.0.0:v1",
    lifespan=lifespan,
)


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(_request: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": "payload_error",
            "message": "Request validation failed",
            "details": exc.errors(),
        },
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

app.include_router(mainRouter)


