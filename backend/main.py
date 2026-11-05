from fastapi import FastAPI

app = FastAPI(title="SMISHGUARD API")


@app.get("/health")
def health():
    return {"status": "ok", "model_ready": False}