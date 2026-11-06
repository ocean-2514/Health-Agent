import React, { useEffect, useState } from 'react';
import {
    ScanSearch, GitMerge, ShieldAlert, Wrench, Send, FileText,
    Stamp, CircleDot, ClipboardList, CheckCircle2, type LucideIcon,
} from 'lucide-react';
import { createWorkorder, fleetTeams, fleetCaSeal, type Workorder, type CaSealInfo } from '../lib/api';
import { useData } from '../lib/store';

// 巡检诊断闭环：证据采集 → 融合研判 → 状态分级 → 检修策略 → 工单生成与跟踪。
// 工单在平台内生成并存档；与检修管理系统对接后可自动推送与加盖电子签章。

type Props = {
    deviceId?: string;
    health: any;
    defect: any;
};

type StageId = 'detect' | 'fusion' | 'grade' | 'strategy' | 'dispatch';

const STAGES: { id: StageId; label: string; sub: string; icon: LucideIcon }[] = [
    { id: 'detect', label: '证据采集', sub: '巡检记录与图像检查', icon: ScanSearch },
    { id: 'fusion', label: '融合研判', sub: '多源证据综合', icon: GitMerge },
    { id: 'grade', label: '状态分级', sub: '异常特征判定', icon: ShieldAlert },
    { id: 'strategy', label: '检修策略', sub: '威胁研判与建议', icon: Wrench },
    { id: 'dispatch', label: '工单流转', sub: '生成与跟踪', icon: Send },
];

const EVIDENCE_LABELS: Record<string, string> = {
    yolo: '图像检查',
    bert: '巡检记录',
    cnn: '油色谱分析',
};

const WORK_TYPES = ['例行巡检建议', '油化跟踪试验', '红外测温复查', '局放复测', '停电检修申请'];
const DEVICE_LABELS: Record<string, string> = {
    tr01: '1号主变压器', tr02: '2号主变压器', tr03: '3号主变压器', tr04: '4号主变压器',
};

function numText(v: any, digits = 1): string {
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(digits) : '—';
}

export default function ReportWorkorder({ deviceId, health, defect }: Props) {
    const [showReport, setShowReport] = useState(false);

    const fusion = defect?.final_fusion_result || {};
    const evidence = defect?.source_evidence || {};
    const evidenceEntries = Object.entries(evidence).filter(
        ([k]) => k !== 'image_url' && k !== 'ai_reasoning' && Boolean(evidence[k]),
    );

    const masses = fusion.all_mass_cn
        ? Object.entries(fusion.all_mass_cn)
              .map(([name, v]) => ({ name, value: Number(v) * 100 }))
              .sort((a, b) => b.value - a.value)
              .slice(0, 3)
        : [];

    const breakdown: { type: string; probability: number }[] = Array.isArray(health?.fault_breakdown)
        ? health.fault_breakdown
        : [];

    const stageReady: Record<StageId, boolean> = {
        detect: evidenceEntries.length > 0 || Boolean(evidence.image_url),
        fusion: Boolean(fusion.final_result_cn),
        grade: Boolean(fusion.final_result_cn),
        strategy: health && Object.keys(health).length > 0,
        dispatch: true,
    };

    const isSample = defect?.data_mode?.mode !== 'realtime';

    return (
        <div className="glass-panel rounded-xl p-5">
            <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                <div className="flex items-center text-[#209F84]">
                    <ClipboardList className="w-4 h-4 mr-2" />
                    <span className="text-sm font-bold uppercase tracking-wider">巡检诊断闭环 · 报告与工单</span>
                </div>
                <button
                    onClick={() => setShowReport((v) => !v)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
                        showReport
                            ? 'bg-[#dceee9] text-[#209F84] border-[#7fc4b8]'
                            : 'bg-[#f8f8fa] text-[#333333] border-[#dcdfe6] hover:bg-[#f2f4f6]'
                    }`}
                >
                    <FileText className="w-3.5 h-3.5" />
                    {showReport ? '收起诊断报告' : '生成诊断报告'}
                </button>
            </div>

            <div className="flex items-center mb-4 overflow-x-auto custom-scrollbar">
                {STAGES.map((s, i) => {
                    const Icon = s.icon;
                    const ready = stageReady[s.id];
                    return (
                        <React.Fragment key={s.id}>
                            <div className="flex items-center flex-shrink-0">
                                <div className={`w-7 h-7 rounded-full flex items-center justify-center border text-[11px] font-bold ${
                                    ready
                                        ? 'border-[#7fc4b8] bg-[#e6f4f0] text-[#209F84]'
                                        : 'border-[#c0c4cc] bg-[#f8f8fa] text-[#666666]'
                                }`}>
                                    {ready ? <Icon className="w-3.5 h-3.5" /> : i + 1}
                                </div>
                                <div className="ml-2 mr-4">
                                    <div className="text-xs text-[#333333] font-semibold whitespace-nowrap">{s.label}</div>
                                    <div className="text-[9px] text-[#666666] whitespace-nowrap">{s.sub}</div>
                                </div>
                            </div>
                            {i < STAGES.length - 1 && (
                                <div className={`flex-1 h-px min-w-6 ${ready ? 'bg-[#cde8e1]' : 'bg-[#f2f4f6]'}`} />
                            )}
                        </React.Fragment>
                    );
                })}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
                <DetectPanel entries={evidenceEntries} evidence={evidence} ready={stageReady.detect} />
                <FusionPanel fusion={fusion} masses={masses} ready={stageReady.fusion} />
                <GradePanel fusion={fusion} overallState={health?.overall_state || defect?.overall_state} ready={stageReady.grade} />
                <StrategyPanel health={health} breakdown={breakdown} ready={stageReady.strategy} />
                <DispatchPanel deviceId={deviceId} health={health} fusion={fusion} />
            </div>

            {showReport && (
                <ReportView
                    deviceId={deviceId}
                    health={health}
                    fusion={fusion}
                    evidenceEntries={evidenceEntries}
                    evidence={evidence}
                    masses={masses}
                    breakdown={breakdown}
                    isSample={isSample}
                    demoNote={defect?.data_mode?.note}
                />
            )}
        </div>
    );
}

function PanelShell({ title, ready, children }: {
    title: string; ready: boolean; children: React.ReactNode;
}) {
    return (
        <div className="rounded-lg border border-[#dcdfe6] bg-[#f8f8fa] p-3 flex flex-col">
            <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-[#333333]">{title}</span>
                <span className={`text-[9px] px-1.5 py-0.5 rounded border ${
                    ready
                        ? 'bg-[#e6f4f0] text-[#209F84] border-[#b3ddd5]'
                        : 'bg-[#f0f2f5] text-[#666666] border-[#dcdfe6]'
                }`}>
                    {ready ? '已有结论' : '待补充'}
                </span>
            </div>
            <div className="flex-1 text-[11px] text-[#333333] leading-relaxed space-y-1.5">{children}</div>
        </div>
    );
}

function DetectPanel({ entries, evidence, ready }: {
    entries: [string, any][]; evidence: any; ready: boolean;
}) {
    return (
        <PanelShell title="① 证据采集" ready={ready}>
            <div className="flex items-center justify-between">
                <span className="text-[#666666]">巡检参考图</span>
                <span className={evidence.image_url ? 'text-[#209F84]' : 'text-[#666666]'}>
                    {evidence.image_url ? '已附' : '暂无'}
                </span>
            </div>
            {entries.length === 0 && <p className="text-[#666666]">暂无单源结论文本。</p>}
            {entries.map(([k, text]) => (
                <div key={k}>
                    <div className="flex items-center justify-between">
                        <span className="text-[#209F84]">{EVIDENCE_LABELS[k] || k}</span>
                        <span className="text-[9px] text-[#d99000]">标准样本</span>
                    </div>
                    <p className="text-[#666666] line-clamp-3">{String(text)}</p>
                </div>
            ))}
        </PanelShell>
    );
}

function FusionPanel({ fusion, masses, ready }: { fusion: any; masses: { name: string; value: number }[]; ready: boolean }) {
    return (
        <PanelShell title="② 融合研判" ready={ready}>
            <div className="flex items-center justify-between">
                <span className="text-[#666666]">综合结论</span>
                <span className={`font-bold ${fusion.is_fault ? 'text-[#ff5b01]' : 'text-[#5ba83c]'}`}>
                    {fusion.final_result_cn || '—'}
                </span>
            </div>
            <div className="flex items-center justify-between">
                <span className="text-[#666666]">置信度</span>
                <span className="font-mono text-[#333333]">{numText(fusion.final_confidence * 100, 1)}%</span>
            </div>
            <div className="space-y-1 pt-1">
                {masses.map((m) => (
                    <div key={m.name} className="flex items-center gap-2">
                        <span className="text-[#666666] w-14 truncate">{m.name}</span>
                        <div className="flex-1 bg-[#f8f8fa] h-1 rounded-full overflow-hidden">
                            <div className="h-full bg-[#209F84]" style={{ width: `${m.value}%` }} />
                        </div>
                        <span className="text-[9px] text-[#666666] font-mono w-12 text-right">{m.value.toFixed(1)}%</span>
                    </div>
                ))}
            </div>
        </PanelShell>
    );
}

function GradePanel({ fusion, overallState, ready }: { fusion: any; overallState: any; ready: boolean }) {
    const hasDltState = Boolean(overallState);
    return (
        <PanelShell title="③ 状态分级" ready={ready}>
            <div className="flex items-center justify-between">
                <span className="text-[#666666]">异常特征</span>
                <span className={fusion.is_fault ? 'text-[#ff5b01] font-semibold' : 'text-[#5ba83c]'}>
                    {fusion.is_fault ? '存在异常特征' : '未见异常特征'}
                </span>
            </div>
            <div className="flex items-center justify-between">
                <span className="text-[#666666]">标准评价状态</span>
                <span className={hasDltState ? 'text-[#d99000]' : 'text-[#666666]'}>
                    {hasDltState ? String(overallState) : '待评价'}
                </span>
            </div>
            <p className="text-[#666666] text-[10px]">正式状态定级（正常 / 注意 / 异常 / 严重）请在「标准评价」页完成。</p>
        </PanelShell>
    );
}

function StrategyPanel({ health, breakdown, ready }: { health: any; breakdown: { type: string; probability: number }[]; ready: boolean }) {
    return (
        <PanelShell title="④ 检修策略" ready={ready}>
            <div className="flex items-center justify-between">
                <span className="text-[#666666]">健康指数</span>
                <span className="font-mono text-[#209F84] font-bold">{numText(health?.health_index)}</span>
            </div>
            <div className="flex items-center justify-between">
                <span className="text-[#666666]">预测剩余寿命</span>
                <span className="font-mono text-[#333333]">{health?.predicted_rul != null ? `${numText(health.predicted_rul)} 年` : '—'}</span>
            </div>
            <div className="flex items-center justify-between">
                <span className="text-[#666666]">主要威胁</span>
                <span className="text-[#333333] truncate max-w-[9rem]">{health?.primary_threat || '—'}</span>
            </div>
            {breakdown.map((b) => (
                <div key={b.type} className="flex items-center gap-2">
                    <span className="text-[#666666] flex-1 truncate">{b.type}</span>
                    <span className="text-[9px] font-mono text-[#666666]">{Number(b.probability).toFixed(1)}%</span>
                </div>
            ))}
            {!health?.diagnosis_summary && <p className="text-[#666666]">暂无补充建议。</p>}
        </PanelShell>
    );
}

function DispatchPanel({ deviceId, health, fusion }: { deviceId?: string; health: any; fusion: any }) {
    const { refreshWorkorders, navigate } = useData();
    const [teams, setTeams] = useState<{ id: string; name: string; skill: string }[]>([]);
    const [team, setTeam] = useState('');
    const [workType, setWorkType] = useState(WORK_TYPES[0]);
    const [priority, setPriority] = useState('一般');
    const [summary, setSummary] = useState('');
    const [creating, setCreating] = useState(false);
    const [error, setError] = useState('');
    const [order, setOrder] = useState<Workorder | null>(null);
    const [seal, setSeal] = useState<CaSealInfo | null>(null);

    useEffect(() => {
        fleetTeams().then((t) => {
            if (t && t.length) { setTeams(t); setTeam(t[0].name); }
        });
        fleetCaSeal().then(setSeal);
    }, []);

    const handleCreate = async () => {
        setCreating(true); setError('');
        try {
            const conclusion = fusion?.final_result_cn ? `研判结论：${fusion.final_result_cn}` : '';
            const res = await createWorkorder({
                equipment_id: deviceId ?? 'tr01',
                work_type: workType,
                summary: summary.trim() || '由系统根据健康评估结果生成的检修建议工单。',
                assignee_team: team,
                priority,
                health_index: typeof health?.health_index === 'number' ? health.health_index : undefined,
                conclusion,
            });
            if (res?.ok) {
                setOrder(res.order);
                await refreshWorkorders();
            } else {
                setError('工单生成失败，请稍后重试。');
            }
        } catch {
            setError('工单生成失败，请稍后重试。');
        } finally {
            setCreating(false);
        }
    };

    return (
        <PanelShell title="⑤ 工单流转" ready={true}>
            {order ? (
                <div className="space-y-1.5">
                    <div className="flex items-center text-[#5ba83c] text-[11px]">
                        <CheckCircle2 className="w-3 h-3 mr-1" /> 工单已生成并存档
                    </div>
                    <div className="flex justify-between"><span className="text-[#666666]">工单编号</span><span className="font-mono text-[#333333]">{order.order_no}</span></div>
                    <div className="flex justify-between"><span className="text-[#666666]">当前状态</span><span className="text-[#d99000]">{order.status}</span></div>
                    <div className="flex justify-between"><span className="text-[#666666]">承办班组</span><span className="text-[#333333]">{order.assignee_team}</span></div>
                    {seal?.available && seal.seal_image && (
                        <div className="flex items-center gap-2 pt-2 border-t border-[#dcdfe6] mt-2">
                            <img src={seal.seal_image} alt="样本签章" className="w-10 h-10 rounded-full object-contain opacity-90" />
                            <p className="text-[10px] text-[#666666] leading-relaxed flex-1">{seal.note}</p>
                        </div>
                    )}
                    <button
                        onClick={() => navigate('approval')}
                        className="w-full mt-2 py-1.5 rounded-lg bg-[#e6f4f0] border border-[#9cd2c7] text-[#209F84] text-[11px] hover:bg-[#dceee9] transition-colors"
                    >
                        前往跟踪复核
                    </button>
                </div>
            ) : (
                <div className="space-y-1.5">
                    <select
                        value={workType}
                        onChange={(e) => setWorkType(e.target.value)}
                        className="w-full bg-[#f8f8fa] border border-[#dcdfe6] rounded px-2 py-1 text-[11px] text-[#333333] focus:outline-none"
                    >
                        {WORK_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                    <select
                        value={team}
                        onChange={(e) => setTeam(e.target.value)}
                        className="w-full bg-[#f8f8fa] border border-[#dcdfe6] rounded px-2 py-1 text-[11px] text-[#333333] focus:outline-none"
                    >
                        {teams.map((t) => <option key={t.id} value={t.name}>{t.name}（{t.skill}）</option>)}
                    </select>
                    <select
                        value={priority}
                        onChange={(e) => setPriority(e.target.value)}
                        className="w-full bg-[#f8f8fa] border border-[#dcdfe6] rounded px-2 py-1 text-[11px] text-[#333333] focus:outline-none"
                    >
                        <option>一般</option><option>紧急</option>
                    </select>
                    <textarea
                        value={summary}
                        onChange={(e) => setSummary(e.target.value)}
                        rows={2}
                        placeholder="补充检修建议（可留空，自动生成摘要）"
                        className="w-full bg-[#f8f8fa] border border-[#dcdfe6] rounded px-2 py-1 text-[11px] text-[#333333] focus:outline-none resize-none"
                    />
                    {error && <p className="text-[10px] text-[#ff5b01]">{error}</p>}
                    <button
                        onClick={handleCreate}
                        disabled={creating}
                        className="w-full py-1.5 rounded-lg bg-[#e6f4f0] border border-[#9cd2c7] text-[#209F84] text-[11px] hover:bg-[#dceee9] transition-colors disabled:opacity-50"
                    >
                        {creating ? '正在生成…' : '生成检修建议工单'}
                    </button>
                    <p className="text-[9px] text-[#666666] flex items-start">
                        <Stamp className="w-3 h-3 mr-1 mt-0.5 flex-shrink-0" />
                        正式签发以检修管理系统电子签章为准。
                    </p>
                </div>
            )}
        </PanelShell>
    );
}

function ReportView({ deviceId, health, fusion, evidenceEntries, evidence, masses, breakdown, isSample, demoNote }: {
    deviceId?: string;
    health: any;
    fusion: any;
    evidenceEntries: [string, any][];
    evidence: any;
    masses: { name: string; value: number }[];
    breakdown: { type: string; probability: number }[];
    isSample: boolean;
    demoNote?: string;
}) {
    const rulValue = typeof health?.predicted_rul === 'number' ? health.predicted_rul : 0;
    const intervalLow = Math.max(1, +(rulValue - 2.2).toFixed(1));
    const intervalHigh = +(rulValue + 3.0).toFixed(1);
    const generatedAt = new Date().toLocaleString('zh-CN', { hour12: false });

    return (
        <div className="mt-4 rounded-lg border border-[#dcdfe6] bg-black/20 p-4">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <div>
                    <div className="text-sm font-bold text-[#333333]">变压器巡检诊断报告（平台汇总稿）</div>
                    <div className="text-[10px] text-[#666666] mt-1">
                        设备名称 {deviceId ? (DEVICE_LABELS[deviceId] ?? deviceId) : '—'} · 生成时间 {generatedAt}
                    </div>
                </div>
                <span className={`text-[10px] px-2 py-1 rounded border ${
                    isSample
                        ? 'bg-[#fdf4e0] text-[#d99000] border-[#f0d9a8]'
                        : 'bg-[#e6f4f0] text-[#209F84] border-[#b3ddd5]'
                }`}>
                    {isSample ? '标准样本数据' : '设备样本数据'}
                </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-[11px]">
                <section>
                    <SectionTitle>1. 检查证据</SectionTitle>
                    {evidenceEntries.length === 0 && <p className="text-[#666666]">暂无单源证据文本。</p>}
                    {evidenceEntries.map(([k, text]) => (
                        <p key={k} className="text-[#333333] mb-1"><span className="text-[#209F84]">{EVIDENCE_LABELS[k] || k}：</span>{String(text)}</p>
                    ))}
                </section>

                <section>
                    <SectionTitle>2. 融合研判结论</SectionTitle>
                    <p className="text-[#333333] mb-1">结论：<span className={fusion.is_fault ? 'text-[#ff5b01]' : 'text-[#5ba83c]'}>{fusion.final_result_cn || '—'}</span></p>
                    <p className="text-[#333333] mb-1">置信度 {numText(fusion.final_confidence * 100, 1)}%</p>
                    {masses.map((m) => <p key={m.name} className="text-[#666666]">{m.name} {m.value.toFixed(1)}%</p>)}
                </section>

                <section>
                    <SectionTitle>3. 健康指数与剩余寿命</SectionTitle>
                    <p className="text-[#333333] mb-1">健康指数：{numText(health?.health_index)}</p>
                    <p className="text-[#333333] mb-1">预测剩余寿命：{health?.predicted_rul != null ? `${numText(health.predicted_rul)} 年` : '—'}</p>
                    <p className="text-[#666666]">样本估算区间：{intervalLow} ~ {intervalHigh} 年（确定性样本口径，非现场实时测量）</p>
                </section>

                <section>
                    <SectionTitle>4. 检修策略与建议</SectionTitle>
                    <p className="text-[#333333] mb-1">主要威胁：{health?.primary_threat || '—'}</p>
                    <p className="text-[#333333] mb-1">风险评分：{health?.risk_score != null ? numText(health.risk_score) : '—'}</p>
                    {breakdown.map((b) => <p key={b.type} className="text-[#666666]">{b.type} {Number(b.probability).toFixed(1)}%</p>)}
                    {health?.diagnosis_summary && (
                        <pre className="whitespace-pre-wrap text-[#666666] text-[10px] mt-1 max-h-32 overflow-y-auto custom-scrollbar font-sans">
                            {String(health.diagnosis_summary)}
                        </pre>
                    )}
                </section>
            </div>

            <section className="mt-3">
                <SectionTitle>5. 工单流转说明</SectionTitle>
                <p className="text-[#666666]">报告对应检修建议工单在平台内生成并存档，可在「专家复核」页查看状态与承办班组；正式签发与电子签章以检修管理系统为准。</p>
            </section>

            {isSample && demoNote && (
                <p className="mt-3 text-[10px] text-[#d99000] leading-relaxed border-t border-[#dcdfe6] pt-2">{demoNote}</p>
            )}
        </div>
    );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex items-center text-[#209F84] text-xs font-bold mb-2">
            <CircleDot className="w-3 h-3 mr-1.5" />
            {children}
        </div>
    );
}
