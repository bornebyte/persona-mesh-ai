from fastapi import FastAPI

app = FastAPI(
    title="Persona Mesh AI API",
    description="A platform for orchestrating configurable AI agents.",
    version="0.1.0",
)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "Persona Mesh AI",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
