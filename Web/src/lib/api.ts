// Simple fetch wrapper to the backend API or returning mock data

const isMock = false; // Set to false to connect to the real Python backend at localhost:8000

export const assessHealth = async (data: any) => {
    if (isMock) {
        // Return a mocked response closely resembling what the engine would produce
        return new Promise(resolve => {
            setTimeout(() => {
                resolve({
                    "health_index": 82.5,
                    "predicted_rul": 24.3,
                    "risk_score": 12.5,
                    "primary_threat": "无显著威胁",
                    "fault_breakdown": [
                        { "type": "过热故障", "probability": 15 },
                        { "type": "放电故障", "probability": 8 }
                    ],
                    "health_deduction_curve": {
                        "x": [2026, 2031, 2036, 2041, 2046, 2051],
                        "y": [82.5, 75, 62, 50, 35, 12]
                    },
                    "fault_risk_curve": {
                        "x": [2026, 2027, 2028, 2029, 2030, 2031, 2032],
                        "y": [12.5, 14, 18, 25, 33, 45, 60]
                    }
                });
            }, 1500);
        });
    }

    const response = await fetch("http://localhost:8000/api/assess/health", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    });
    return response.json();
};

export const assessDefect = async (data: any) => {
    if (isMock) {
        return new Promise(resolve => {
            setTimeout(() => {
                const res = {
                    "final_fusion_result": {
                        "final_result_cn": data.id === 'tr01' ? "起火" : (data.id === 'tr02' ? "漏油" : "正常"),
                        "final_confidence": data.id === 'tr01' ? 0.9821 : (data.id === 'tr02' ? 0.9421 : 0.9950),
                        "is_definite": true,
                    },
                    "source_evidence": {
                        "bert": data.id === 'tr01' ? "日志检测到：设备温度急剧上升，触发火灾告警" : (data.id === 'tr02' ? "日志检测到：变压器外壳出现油污记录" : "日志记录：设备运行参数一切正常"),
                        "cnn": "油色谱分析：组分比例正常",
                        "yolo": data.id === 'tr01' ? "视觉检测成果：识别到明显明火及浓烟" : (data.id === 'tr02' ? "视觉检测成果：在变压器基座检测到显著油污喷溅" : "视觉检测成果：设备外观清洁度正常"),
                        "image_url": data.id === 'tr01' ? "/assets/defects/fire_defect.png" : (data.id === 'tr02' ? "/assets/defects/oil_leakage.png" : "/assets/defects/normal_sample.png")
                    }
                };
                resolve(res);
            }, 1000);
        });
    }
    const response = await fetch("http://localhost:8000/api/assess/defect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    });
    return response.json();
}
