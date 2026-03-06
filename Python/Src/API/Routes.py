from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

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
