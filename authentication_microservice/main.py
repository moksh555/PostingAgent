from fastapi import FastAPI #type: ignore
from app.api.router import router as mainRouter
from fastapi.middleware.cors import CORSMiddleware #type: ignore


app = FastAPI(
    title="Authentication Microservice - User Authentication",
    version="1.0.0:v1",
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


