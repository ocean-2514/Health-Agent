import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys
from pathlib import Path

# Fix relative imports
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from Python.Src.API.Routes import router
from Python.Src.API.AgentRoutes import router as agent_router
from Python.Src.Middleware.GlobalConfig import GlobalConfig
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="ElectricityHealthAgent Integrated API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mock_dir = Path(project_root) / "mock"
mock_dir.mkdir(exist_ok=True)
app.mount("/mock", StaticFiles(directory=str(mock_dir)), name="mock")

app.include_router(router)
app.include_router(agent_router)

if __name__ == "__main__":
    server_config = GlobalConfig.config.get("Server", {})
    host = server_config.get("Host", "0.0.0.0")
    port = server_config.get("Port", 8000)
    
    print(f"Starting server on {host}:{port}")
    uvicorn.run("Main:app", host=host, port=port, reload=True)
