from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Services.AssessmentService import AssessmentService

router = APIRouter()
assessment_service = AssessmentService()

class DefectReq(BaseModel):
    id: Optional[str] = "tr01"
    substation_id: Optional[str] = "station1"
    bert_json: Optional[str] = None
    cnn_json: Optional[str] = None
    yolo_json: Optional[str] = None

class HealthInput(BaseModel):
    id: Optional[str] = "tr01"
    substation_id: Optional[str] = "station1"
    oil_bdv: int = 2
    oil_water: int = 2
    oil_acid: int = 1
    oil_ift: int = 2
    dga_h2: int = 2
    dga_ch4: int = 2
    dga_co: int = 1
    dga_co2: int = 1
    dga_c2h4: int = 1
    dga_c2h6: int = 1
    dga_c2h2: int = 1
    furan_level: str = "A"
    future_load: float = 0.8
    ambient_temp: float = 25.0
    moisture: Optional[float] = None
    penalty_factor: Optional[float] = 1.0

@router.post("/api/assess/defect")
async def assess_defect(req: DefectReq):
    try:
        data = assessment_service.run_defect_identification(req.dict())
        return data
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/assess/health")
async def assess_health(req: HealthInput):
    try:
        data = assessment_service.run_health_assessment(req.dict())
        return data
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/health")
async def ping():
    return {"status": "ok", "message": "ElectricityHealthAgent is running."}

@router.get("/")
async def root():
    """API 根路径，返回API信息"""
    return {
        "service": "Electricity Health Agent",
        "version": "1.0.0",
        "status": "running",
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc"
        },
        "available_endpoints": [
            {"path": "/api/health", "method": "GET", "description": "健康检查"},
            {"path": "/api/assess/defect", "method": "POST", "description": "缺陷识别"},
            {"path": "/api/assess/health", "method": "POST", "description": "健康评估"}
        ]
    }

if __name__ == "__main__":
    req = HealthInput()
    print(req.dict())