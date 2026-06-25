// Simple fetch wrapper to the backend API or returning mock data

const isMock = false; // Set to false to connect to the real Python backend at localhost:8000

export const API_BASE = "http://localhost:8000";

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

// ===========================================================================
// Multi-agent platform (Supervisor) — the refactored Tool/Skill/Agent stack
// ===========================================================================

export type ToolCall = { name: string; args: Record<string, any> };

export type AgentChatResp = {
    session_id: string;
    answer: string;
    tool_calls: ToolCall[];
};

export type CatalogueItem = { name: string; description: string; disabled?: boolean };

export type AgentCatalogue = { tools: CatalogueItem[]; skills: CatalogueItem[] };

/** One chat turn. Pass `session_id` to continue a conversation; omit it to
 * start a new one (the returned `session_id` is the created/used id). */
export const agentChat = async (
    message: string,
    sessionId?: string
): Promise<AgentChatResp> => {
    const response = await fetch(`${API_BASE}/api/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId ?? null }),
    });
    if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail?.detail || `请求失败 (${response.status})`);
    }
    return response.json();
};

export const agentNewSession = async (): Promise<string> => {
    const response = await fetch(`${API_BASE}/api/agent/session`, { method: "POST" });
    const data = await response.json();
    return data.session_id;
};

export const agentHistory = async (
    sessionId: string
): Promise<{ role: string; content: string }[]> => {
    const response = await fetch(`${API_BASE}/api/agent/session/${sessionId}/history`);
    if (!response.ok) return [];
    const data = await response.json();
    return data.messages ?? [];
};

export const agentCatalogue = async (): Promise<AgentCatalogue> => {
    const response = await fetch(`${API_BASE}/api/agent/catalogue`);
    if (!response.ok) return { tools: [], skills: [] };
    return response.json();
};

export type SessionInfo = {
    session_id: string;
    created_at: string;
    last_active: string;
    message_count: number;
};

export const agentSessions = async (limit = 30): Promise<SessionInfo[]> => {
    const response = await fetch(`${API_BASE}/api/agent/sessions?limit=${limit}`);
    if (!response.ok) return [];
    const data = await response.json();
    return data.sessions ?? [];
};

export const agentDeleteSession = async (sessionId: string): Promise<void> => {
    await fetch(`${API_BASE}/api/agent/session/${sessionId}`, { method: 'DELETE' });
};

// ---- hot-loading (mutates the live registry, returns fresh catalogue) ----

/** Catalogue + optional mutation metadata (added names / registered name). */
export type MutationResult = AgentCatalogue & {
    added?: string[];
    registered?: string;
    changed?: boolean;
};

const postMutation = async (path: string, body?: any): Promise<MutationResult> => {
    const response = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
    });
    if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail?.detail || `请求失败 (${response.status})`);
    }
    return response.json();
};

export const agentReloadSkills = (): Promise<MutationResult> =>
    postMutation('/api/agent/reload_skills');

export const agentRegisterRemote = (url: string, name?: string): Promise<MutationResult> =>
    postMutation('/api/agent/tools/register_remote', { url, name: name ?? null });

export const agentReloadRemote = (): Promise<MutationResult> =>
    postMutation('/api/agent/tools/reload_remote');

export const agentLoadDir = (path: string): Promise<MutationResult> =>
    postMutation('/api/agent/tools/load_dir', { path });

export const agentEnableTool = (name: string): Promise<MutationResult> =>
    postMutation(`/api/agent/tools/${name}/enable`);

export const agentDisableTool = (name: string): Promise<MutationResult> =>
    postMutation(`/api/agent/tools/${name}/disable`);

export const agentRemoveTool = async (name: string): Promise<MutationResult> => {
    const response = await fetch(`${API_BASE}/api/agent/tools/${name}`, { method: 'DELETE' });
    if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail?.detail || `请求失败 (${response.status})`);
    }
    return response.json();
};
