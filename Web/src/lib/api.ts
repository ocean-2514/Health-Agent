// HTTP wrapper to the real Python backend (FastAPI :8000).
// 同源相对路径：构建后 SPA 由 FastAPI 直接托管；npm run dev 时 Vite 把 /api、/edge 代理到 :8000。
export const API_BASE = "";

const jsonPost = async (path: string, body: unknown) => {
    const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    return response.json();
};

export const assessHealth = (data: any) => jsonPost("/api/assess/health", data);

export const assessDefect = (data: any) => jsonPost("/api/assess/defect", data);

// ===========================================================================
// Multi-agent platform (Supervisor) — the refactored Tool/Skill/Agent stack
// ===========================================================================

export type ToolCall = { name: string; args: Record<string, any> };

// Fixed closed vocabularies — mirror the backend planner/guard enums.
export type IntentId =
    | 'defect_detection'
    | 'dga_interpretation'
    | 'history_query'
    | 'knowledge_retrieval'
    | 'diagnosis'
    | 'report_workorder'
    | 'chitchat';

export type RoleId = 'perception' | 'diagnosis' | 'compliance' | 'decision' | 'knowledge';

export type StepStatus = 'pending' | 'running' | 'done' | 'error';

export type IntentInfo = {
    intent: IntentId;
    label: string;
    confidence: number;
    source: 'rule' | 'llm';
    needs_plan: boolean;
};

export type PlanStep = {
    step_id: string;
    label: string;
    tool: string;
    role: RoleId;
    reason: string;
    status: StepStatus;
    args?: Record<string, any>;
};

export type Plan = { steps: PlanStep[] };

export type GuardCheck = {
    claim: string;
    grounded: boolean;
    detail: string;
};

export type GuardResult = {
    passed: boolean;
    action: 'pass' | 'blocked' | 'corrected';
    checks: GuardCheck[];
    message: string;
};

// One real per-image detection carried by the evidence event/field.
export type EvidenceDetection = {
    class: string;
    confidence: number;
};

export type EvidenceRecord = {
    image_index: number;
    tool: string;
    online: boolean;
    ok: boolean;
    summary: string;
    detections: EvidenceDetection[];
};

export type AgentChatResp = {
    session_id: string;
    answer: string;
    tool_calls: ToolCall[];
    intent?: IntentInfo | null;
    plan?: Plan | null;
    guard?: GuardResult | null;
    evidence?: EvidenceRecord[];
};

export type CatalogueItem = { name: string; description: string; disabled?: boolean; builtin?: boolean };

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

// ---- streaming chat (SSE over fetch) ----

export type AgentStreamEvent =
    | { type: "session"; session_id: string }
    | { type: "intent"; intent: IntentId; label: string; confidence: number; source: 'rule' | 'llm'; needs_plan: boolean }
    | { type: "plan"; steps: PlanStep[] }
    | { type: "evidence"; records: EvidenceRecord[] }
    | { type: "text"; delta: string }
    | { type: "tool_call"; name: string; args: Record<string, any>; step_id?: string; role?: RoleId; title?: string }
    | { type: "tool_result"; name: string; ok: boolean; step_id?: string; role?: RoleId }
    | { type: "guard"; passed: boolean; action: 'pass' | 'blocked' | 'corrected'; checks: GuardCheck[]; message: string }
    | { type: "final"; answer: string; tool_calls: ToolCall[] }
    | { type: "error"; message: string }
    | { type: "end" };

/** Stream one chat turn. Calls `onEvent` for each SSE event. Returns when the
 * stream ends. EventSource only supports GET, so we POST + parse the body.
 * `imagePaths` are local paths returned by agentUploadImage. */
export const agentChatStream = async (
    message: string,
    sessionId: string | undefined,
    onEvent: (ev: AgentStreamEvent) => void,
    signal?: AbortSignal,
    imagePaths?: string[],
): Promise<void> => {
    const resp = await fetch(`${API_BASE}/api/agent/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            message,
            session_id: sessionId ?? null,
            image_paths: imagePaths ?? [],
        }),
        signal,
    });
    if (!resp.ok || !resp.body) {
        const detail = await resp.json().catch(() => ({}));
        throw new Error(detail?.detail || `请求失败 (${resp.status})`);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx: number;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
            const frame = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            const line = frame.split("\n").find((l) => l.startsWith("data:"));
            if (!line) continue;
            const json = line.slice(5).trim();
            if (!json) continue;
            try {
                onEvent(JSON.parse(json) as AgentStreamEvent);
            } catch {
                /* ignore malformed frame */
            }
        }
    }
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
    title?: string;
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

// ===========================================================================
// DL/T 1685-2017 standard state-evaluation ("标准评价" page)
// ===========================================================================

export type DltItem = {
    key: string;
    name: string;
    group?: string | null;
    input: 'numeric' | 'qualitative';
    levels: string[];
    hint: string;
};

export type DltComponent = { component: string; items: DltItem[] };

export type DltCatalogue = {
    components: DltComponent[];
    levels_all: string[];
    voltage_options: number[];
};

export type DltComponentResult = {
    state: string;
    total_deduction: number;
    max_single: number;
    items: { item: string; level: string; deduction: number; basis: string }[];
};

export type DltEvalResult = {
    overall_state: string;
    total_deduction: number;
    health_index: number;
    components: Record<string, DltComponentResult>;
};

export type DltMeasurements = Record<string, string | number>;

export const dltCatalogue = async (): Promise<DltCatalogue> => {
    const r = await fetch(`${API_BASE}/api/dlt1685/catalogue`);
    if (!r.ok) throw new Error(`加载状态量目录失败 (${r.status})`);
    return r.json();
};

export const dltEvaluate = async (
    measurements: DltMeasurements,
    voltageKv: number,
): Promise<DltEvalResult> => {
    const r = await fetch(`${API_BASE}/api/dlt1685/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ measurements, voltage_kv: voltageKv }),
    });
    if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d?.detail || `评价失败 (${r.status})`);
    }
    return r.json();
};

export type DltImportResult = {
    equipment_id: string;
    measurements: DltMeasurements;
    imported: { key: string; name: string; value: number; sensor: string }[];
};

export const dltIotdbImport = async (
    equipmentId: string,
    substation = 'station1',
): Promise<DltImportResult> => {
    const r = await fetch(
        `${API_BASE}/api/dlt1685/iotdb_import?equipment_id=${encodeURIComponent(equipmentId)}&substation=${encodeURIComponent(substation)}`,
    );
    if (!r.ok) throw new Error(`测点数据导入失败，请检查数据文件后重试（状态码 ${r.status}）`);
    return r.json();
};

export type DltDiagnoseResult = {
    health_index: number;
    predicted_rul_years: number;
    fusion_verdict_cn: string;
    fusion_confidence: number;
    dga_risk_score?: number | null;
    primary_threat?: string | null;
    forced_override?: string | null;
    overall_state?: string | null;
    dlt_evaluation?: DltEvalResult | null;
    final_report: string;
};

export const dltDiagnose = async (
    equipmentId: string,
    measurements: DltMeasurements,
    voltageKv: number,
    substation = 'station1',
): Promise<DltDiagnoseResult> => {
    const r = await fetch(`${API_BASE}/api/dlt1685/diagnose`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            equipment_id: equipmentId,
            substation,
            measurements,
            voltage_kv: voltageKv,
        }),
    });
    if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d?.detail || `诊断失败 (${r.status})`);
    }
    return r.json();
};

// ===========================================================================
// Image upload and on-site visual analysis proxy.
// ===========================================================================

export type UploadedImage = {
    path: string;
    filename: string;
    size: number;
    url: string;
};

/** Upload one image to the brain. Returns the local path the edge tools read
 * (same host) and a same-origin URL for in-chat preview. */
export const agentUploadImage = async (file: File): Promise<UploadedImage> => {
    const form = new FormData();
    form.append("file", file);
    const r = await fetch(`${API_BASE}/api/agent/upload`, {
        method: "POST",
        body: form,
    });
    if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d?.detail || `图片上传失败 (${r.status})`);
    }
    return r.json();
};

// ---- edge gateway types ----

export type EdgeCamera = {
    id: string;
    name: string;
    location: string;
    rtsp_url: string;
    status: string;
    algorithms: string[];
    create_time?: string;
};

export type DemoSource = { name: string; source: string };

export type DemoSourcesResp = {
    dir: string;
    available: boolean;
    sources: DemoSource[];
};

const edgeGet = async <T>(path: string): Promise<T> => {
    const r = await fetch(`${API_BASE}${path}`);
    if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d?.detail || `请求失败 (${r.status})`);
    }
    return r.json();
};

const edgePost = async <T>(path: string, body?: unknown): Promise<T> => {
    const r = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d?.detail || `请求失败 (${r.status})`);
    }
    return r.json();
};

export const edgeDemoSources = () =>
    edgeGet<DemoSourcesResp>("/api/edge/demo_sources");

export const edgeCameras = () => edgeGet<EdgeCamera[]>("/edge/api/cameras");

export type StreamStartResp = {
    success: boolean;
    cam_id: string;
    stream_url: string;
};

/** Start a camera preview. `source` is a prepared sample video or an approved
 * live address supplied by the operations team. */
export const edgeStreamStart = (
    camId: string,
    source: string,
    modelType: string,
) =>
    edgePost<StreamStartResp>(`/edge/api/stream/start/${camId}`, {
        source,
        model_type: modelType,
    });

export const edgeStreamStop = (camId: string) =>
    edgePost<{ success: boolean }>(
        `/edge/api/stream/stop/${camId}`,
    );

/** Browser URL for a running MJPEG stream (proxied through the brain). */
export const edgeStreamUrl = (camId: string) =>
    `${API_BASE}/edge/api/stream/${camId}`;

/** Browser URL for a single JPEG snapshot. */
export const edgeSnapshotUrl = (camId: string) =>
    `${API_BASE}/edge/api/cameras/${camId}/snapshot`;

// ---- real edge alarms (replaces the old fabricated warning stream) ----

export type EdgeAlarm = {
    id: string;
    camera_id: string;
    camera_name: string;
    algorithm_id: string;
    algorithm_name: string;
    image_url: string;
    result: string;
    confidence: number;
    severity: string;
    review_status: string;
    review_result: string;
    create_time: string;
};

/** Fetch the real edge alarm list through the brain gateway. */
export const edgeAlarms = (): Promise<EdgeAlarm[]> =>
    edgeGet<EdgeAlarm[]>("/edge/api/alarms");

// ===========================================================================
// 综合评估首页聚合（台账 / 健康概览 / 多模态样本 / 工单台账 / 标准评价回写）
// ===========================================================================

export type SourceInfo = {
    code: string;
    label: string;
    realtime: boolean;
    dataset_dir?: string;
};

export type SeriesXY = { x: Array<number | string>; y: number[] };

export type FleetDevice = {
    equipment_id: string;
    name: string;
    station_id: string;
    station_name: string;
    health_index: number;
    rul_years: number;
    risk_score: number;
    primary_threat: string | null;
    fusion_verdict: string;
    status: "正常" | "关注" | "异常" | "严重" | string;
    dlt_state: string | null;
    dlt_deduction: number | null;
    dlt_updated_at?: string | null;
    open_orders: number;
    modal_status: { ir: string; pd: string; vib: string };
    model: string;
    commission_date: string;
    risk_curve: SeriesXY;
    health_curve: SeriesXY;
};

export type FleetStation = {
    id: string;
    name: string;
    voltage_kv: number;
    devices: FleetDevice[];
};

export type FleetOverview = {
    generated_at: string;
    data_source: SourceInfo;
    stations: FleetStation[];
    summary: {
        device_total: number;
        status_counts: Record<string, number>;
        open_orders: number;
        avg_hi: number;
    };
    fleet_risk_curve: SeriesXY;
    fleet_hi_curve: SeriesXY;
    maintenance_history: Record<string, Array<{ date: string; type: string; result: string; operator: string }>>;
};

export type Workorder = {
    order_no: string;
    equipment_id: string;
    equipment_name: string;
    station_id: string;
    work_type: string;
    summary: string;
    conclusion?: string;
    priority: string;
    assignee_team: string;
    status: string;
    health_index?: number | null;
    created_at: string;
    signed: boolean;
    note: string;
    data_source?: SourceInfo;
};

export type Ledger = {
    equipment_id: string;
    name: string;
    station_name: string;
    model: string;
    voltage_kv: number;
    capacity_mva: number;
    manufacturer: string;
    commission_date: string;
    cooling: string;
    oil_volume_m3: number;
    serial_no?: string | null;
    vector_group?: string | null;
    insulation_level?: string | null;
    tap_changer_model?: string | null;
    operation_status?: string | null;
    last_maintenance_date?: string | null;
    remark?: string | null;
    data_source: SourceInfo;
};

export type ModalSample = {
    kind: string;
    title: string;
    overall_status: string;
    data_source: SourceInfo;
    [k: string]: any;
};

export type DeviceModalities = {
    equipment_id: string;
    ir: ModalSample;
    pd: ModalSample;
    vib: ModalSample;
    temp_load: ModalSample;
    data_source: SourceInfo;
};

export type DgaGasSeries = { values: number[]; timestamps: string[]; unit: string };

export type DgaPublicSeries = {
    equipment_id: string;
    sample_count: number;
    dates: string[];
    gases: Record<string, DgaGasSeries>;
    latest: Record<string, number>;
    condition_label: string;
    diagnosis_basis: string;
    oil_temp_c?: string | null;
    load_rate_pct?: string | null;
    note: string;
    data_source: SourceInfo;
};

export type ReviewTask = {
    id: string;
    title: string;
    device_id: string;
    device: string;
    station: string;
    time: string;
    desc: string;
    health: number;
    risk: number;
    status_level: string;
    decision?: 'approved' | 'rejected' | null;
    decision_note?: string;
    decided_at?: string;
};

export type DatasetSource = {
    source_id: string;
    title: string;
    publisher: string;
    url: string;
    role: string;
};

export type DatasetManifest = {
    manifest_version?: string;
    generated_at?: string;
    disclaimer: string;
    source_count: number;
    sources: DatasetSource[];
    data_source: SourceInfo;
};

export type CaSealInfo = {
    available: boolean;
    seal_image: string | null;
    issued_by: string;
    issued_at?: string;
    note: string;
    data_source: SourceInfo;
};

/** 聚合接口允许后端短暂不可用：返回 null 由前端渲染“稍后重试”空状态，不抛白屏。 */
const safeGet = async <T,>(path: string): Promise<T | null> => {
    try {
        const r = await fetch(`${API_BASE}${path}`);
        if (!r.ok) return null;
        return (await r.json()) as T;
    } catch {
        return null;
    }
};

const safePost = async <T,>(path: string, body?: unknown): Promise<T | null> => {
    try {
        const r = await fetch(`${API_BASE}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: body === undefined ? undefined : JSON.stringify(body),
        });
        if (!r.ok) return null;
        return (await r.json()) as T;
    } catch {
        return null;
    }
};

export const fleetOverview = () => safeGet<FleetOverview>("/api/fleet/overview");
export const deviceLedger = (id: string) => safeGet<Ledger>(`/api/fleet/devices/${id}/ledger`);
export const deviceModalities = (id: string) => safeGet<DeviceModalities>(`/api/fleet/devices/${id}/modalities`);
export const deviceDga = (id: string) => safeGet<DgaPublicSeries>(`/api/fleet/devices/${id}/dga`);
export const deviceHistory = (id: string) =>
    safeGet<{ equipment_id: string; records: Array<{ date: string; type: string; result: string; operator: string }> }>(
        `/api/fleet/devices/${id}/history`,
    );
export const listWorkorders = () => safeGet<{ total: number; open: number; items: Workorder[] }>("/api/fleet/workorders");

export const createWorkorder = (body: {
    equipment_id: string;
    work_type: string;
    summary?: string;
    assignee_team?: string;
    priority?: string;
    health_index?: number;
    conclusion?: string;
}) => safePost<{ ok: boolean; order: Workorder }>("/api/fleet/workorders", body);

export const advanceWorkorder = (orderNo: string, status: string) =>
    safePost<{ ok: boolean; order: Workorder }>(`/api/fleet/workorders/${encodeURIComponent(orderNo)}/status`, { status });

export const recordDltResult = (body: {
    equipment_id: string;
    overall_state?: string | null;
    health_index?: number | null;
    total_deduction?: number | null;
    components?: Record<string, any>;
}) => safePost<{ ok: boolean; equipment_id: string }>("/api/fleet/dlt_result", body);

export const reviewTasks = () => safeGet<{ items: ReviewTask[]; data_source: SourceInfo }>("/api/fleet/review_tasks");
export const fleetDatasetManifest = () => safeGet<DatasetManifest>("/api/fleet/dataset_manifest");
export const fleetCaSeal = () => safeGet<CaSealInfo>("/api/fleet/ca_seal");

export const submitReviewDecision = (taskId: string, decision: 'approved' | 'rejected', note = '') =>
    safePost<{ ok: boolean; task_id: string; decision: { decision: string; note: string; decided_at: string } }>(
        `/api/fleet/review_tasks/${encodeURIComponent(taskId)}/decision`,
        { decision, note },
    );

export type Team = { id: string; name: string; skill: string };
export const fleetTeams = () => safeGet<Team[]>("/api/fleet/teams");

// ===========================================================================
// 中台（知识平台 :5000）同源网关 —— 供“知识管理”栏目原生取数
// ===========================================================================

const middleGet = async <T,>(path: string): Promise<T | null> => {
    try {
        const r = await fetch(`${API_BASE}${path}`);
        if (!r.ok) return null;
        return (await r.json()) as T;
    } catch {
        return null;
    }
};

const middlePost = async <T,>(path: string, body?: unknown): Promise<T | null> => {
    try {
        const r = await fetch(`${API_BASE}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: body === undefined ? undefined : JSON.stringify(body),
        });
        if (!r.ok) return null;
        return (await r.json()) as T;
    } catch {
        return null;
    }
};

export type MiddleDatasetSummary = {
    ok: boolean;
    summary: {
        total_files: number;
        pdf_count: number;
        image_count: number;
        category_count: number;
        custom_category_count: number;
        unknown_name_count: number;
        new_files_7d: number;
        deleted_count: number;
    };
};

export type MiddlePdfItem = {
    id?: string;
    name: string;
    file_type?: string;
    category?: string;
    content_lv1?: string;
    size?: number;
    upload_time?: string | number;
    [k: string]: any;
};

export type MiddleQaResp = {
    ok?: boolean;
    answer?: string;
    cited_answer?: string;
    citation_references?: Array<{ title?: string; [k: string]: any }>;
    answer_sources?: string[];
    evidence_chunks?: any[];
    [k: string]: any;
};

export const middleDatasetSummary = () =>
    middleGet<MiddleDatasetSummary>("/middle/api/datasets/summary");

export const middleDatasetDistribution = () =>
    middleGet<Record<string, any>>("/middle/api/datasets/distribution");

export const middlePdfs = () =>
    middleGet<{ ok?: boolean; pdfs?: MiddlePdfItem[]; items?: MiddlePdfItem[] } | MiddlePdfItem[]>(
        "/middle/api/pdfs",
    );

export const middleGraphOverview = () =>
    middleGet<Record<string, any>>("/middle/api/graph/overview");

export const middleQaAsk = (question: string) =>
    middlePost<MiddleQaResp>("/middle/api/qa/ask", { question });

// ===========================================================================
// 边缘（:8080）系统管理取数 —— 供“系统管理”栏目原生取数
// ===========================================================================

export const edgeModelStats = () =>
    edgeGet<Record<string, any>>("/edge/api/model/stats").catch(() => null);

export const edgeSystemStats = () =>
    edgeGet<Record<string, any>>("/edge/api/system/stats").catch(() => null);

export const edgeGpuStatus = () =>
    edgeGet<Record<string, any>>("/edge/api/gpu_status").catch(() => null);

export const edgeHalProbe = () =>
    edgeGet<Record<string, any>>("/edge/api/hal/probe").catch(() => null);

export const edgeUsers = () =>
    edgeGet<Record<string, any>>("/edge/api/users").catch(() => null);

export const edgeLlmStatus = () =>
    edgeGet<Record<string, any>>("/edge/api/llm/status").catch(() => null);

export const edgeHealth = () =>
    edgeGet<{ status?: string; [k: string]: any }>("/edge/health").catch(() => null);
