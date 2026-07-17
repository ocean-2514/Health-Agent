import React, { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
    ClipboardList, Database, Calculator, Activity, Eraser,
    Loader2, ChevronDown, ChevronRight, ShieldCheck,
} from 'lucide-react';
import {
    dltCatalogue, dltEvaluate, dltIotdbImport, dltDiagnose,
    type DltCatalogue, type DltComponent, type DltMeasurements,
    type DltEvalResult, type DltDiagnoseResult,
} from '../lib/api';

const EQUIPMENT = ['tr01', 'tr02', 'tr03', 'tr04'];

// Standard state → accent color.
const STATE_STYLE: Record<string, { text: string; bg: string; ring: string; dot: string }> = {
    正常: { text: 'text-emerald-300', bg: 'bg-emerald-500/10', ring: 'border-emerald-500/30', dot: 'bg-emerald-400' },
    注意: { text: 'text-amber-300', bg: 'bg-amber-500/10', ring: 'border-amber-500/30', dot: 'bg-amber-400' },
    异常: { text: 'text-orange-300', bg: 'bg-orange-500/10', ring: 'border-orange-500/30', dot: 'bg-orange-400' },
    严重: { text: 'text-red-300', bg: 'bg-red-500/10', ring: 'border-red-500/30', dot: 'bg-red-400' },
};
const stateStyle = (s?: string) => STATE_STYLE[s || '正常'] || STATE_STYLE['正常'];

type Props = {
    equipmentId: string;
    onEquipmentChange: (id: string) => void;
};

export default function DltEvaluation({ equipmentId, onEquipmentChange }: Props) {
    const [cat, setCat] = useState<DltCatalogue | null>(null);
    const [values, setValues] = useState<DltMeasurements>({});
    const [voltage, setVoltage] = useState(220);
    const [evalRes, setEvalRes] = useState<DltEvalResult | null>(null);
    const [diagRes, setDiagRes] = useState<DltDiagnoseResult | null>(null);
    const [busy, setBusy] = useState<'' | 'eval' | 'diag' | 'import'>('');
    const [err, setErr] = useState<string | null>(null);
    const [note, setNote] = useState<string | null>(null);
    const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

    useEffect(() => {
        dltCatalogue().then(setCat).catch((e) => setErr(e.message));
    }, []);

    // components that actually carry state quantities
    const components: DltComponent[] = useMemo(
        () => (cat?.components || []).filter((c) => c.items.length > 0),
        [cat],
    );

    const filledCount = useMemo(
        () => Object.values(values).filter((v) => v !== '' && v !== '正常' && v != null).length,
        [values],
    );

    const setVal = (key: string, v: string) =>
        setValues((prev) => ({ ...prev, [key]: v }));

    const cleaned = (): DltMeasurements => {
        const out: DltMeasurements = {};
        for (const [k, v] of Object.entries(values)) {
            if (v === '' || v === '正常' || v == null) continue;
            const item = itemByKey.get(k);
            out[k] = item?.input === 'numeric' ? Number(v) : v;
        }
        return out;
    };

    const itemByKey = useMemo(() => {
        const m = new Map<string, DltCatalogue['components'][0]['items'][0]>();
        for (const c of cat?.components || []) for (const it of c.items) m.set(it.key, it);
        return m;
    }, [cat]);

    const runEvaluate = async () => {
        setBusy('eval'); setErr(null); setNote(null); setDiagRes(null);
        try {
            setEvalRes(await dltEvaluate(cleaned(), voltage));
        } catch (e: any) { setErr(e.message); } finally { setBusy(''); }
    };

    const runDiagnose = async () => {
        setBusy('diag'); setErr(null); setNote(null);
        try {
            const r = await dltDiagnose(equipmentId, cleaned(), voltage);
            setDiagRes(r);
            if (r.dlt_evaluation) setEvalRes(r.dlt_evaluation);
        } catch (e: any) { setErr(e.message); } finally { setBusy(''); }
    };

    const runImport = async () => {
        setBusy('import'); setErr(null); setNote(null);
        try {
            const r = await dltIotdbImport(equipmentId);
            setValues((prev) => ({ ...prev, ...r.measurements }));
            setNote(
                r.imported.length
                    ? `已从 IoTDB 导入 ${r.imported.length} 项: ${r.imported.map((i) => `${i.name}=${i.value}`).join('、')}`
                    : '该设备没有可映射到 DL/T 状态量的 IoTDB 测点',
            );
        } catch (e: any) { setErr(e.message); } finally { setBusy(''); }
    };

    const clearAll = () => { setValues({}); setEvalRes(null); setDiagRes(null); setNote(null); setErr(null); };

    const disabled = busy !== '';

    return (
        <div className="h-full flex gap-4">
            {/* ============ Input form ============ */}
            <div className="flex-1 flex flex-col glass-panel rounded-2xl overflow-hidden min-w-0">
                <div className="flex items-center justify-between px-5 py-3 border-b border-white/10 flex-shrink-0 flex-wrap gap-2">
                    <div className="flex items-center text-cyan-400 font-medium">
                        <ClipboardList className="w-4 h-4 mr-2" />
                        DL/T 1685-2017 状态量录入
                        <span className="ml-3 text-xs text-gray-500">已填 {filledCount} 项 · 未填按“不扣分”计</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                        <label className="text-gray-500">设备</label>
                        <select
                            value={equipmentId}
                            onChange={(e) => onEquipmentChange(e.target.value)}
                            className="bg-white/5 border border-white/10 rounded-lg px-2 py-1 focus:outline-none focus:border-cyan-500/50"
                        >
                            {EQUIPMENT.map((d) => <option key={d} value={d} className="bg-[#0A0B10]">{d}</option>)}
                        </select>
                        <label className="text-gray-500 ml-1">电压</label>
                        <select
                            value={voltage}
                            onChange={(e) => setVoltage(Number(e.target.value))}
                            className="bg-white/5 border border-white/10 rounded-lg px-2 py-1 focus:outline-none focus:border-cyan-500/50"
                        >
                            {(cat?.voltage_options || [110, 220, 330, 500]).map((v) =>
                                <option key={v} value={v} className="bg-[#0A0B10]">{v}kV</option>)}
                        </select>
                    </div>
                </div>

                {/* toolbar */}
                <div className="flex items-center gap-2 px-5 py-2.5 border-b border-white/10 flex-shrink-0 flex-wrap">
                    <ToolButton onClick={runImport} busy={busy === 'import'} disabled={disabled} icon={<Database className="w-3.5 h-3.5" />} tone="slate">
                        从 IoTDB 导入
                    </ToolButton>
                    <ToolButton onClick={runEvaluate} busy={busy === 'eval'} disabled={disabled} icon={<Calculator className="w-3.5 h-3.5" />} tone="cyan">
                        计算评分
                    </ToolButton>
                    <ToolButton onClick={runDiagnose} busy={busy === 'diag'} disabled={disabled} icon={<Activity className="w-3.5 h-3.5" />} tone="violet">
                        完整诊断
                    </ToolButton>
                    <div className="ml-auto flex items-center gap-2">
                        <ToolButton onClick={clearAll} disabled={disabled} icon={<Eraser className="w-3.5 h-3.5" />} tone="slate">
                            清空
                        </ToolButton>
                    </div>
                </div>

                {(err || note) && (
                    <div className={`mx-5 mt-3 rounded-lg px-3 py-2 text-xs border ${err ? 'text-red-300 border-red-500/20 bg-red-500/5' : 'text-emerald-300 border-emerald-500/20 bg-emerald-500/5'}`}>
                        {err || note}
                    </div>
                )}

                <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
                    {!cat && <p className="text-sm text-gray-500 p-4">加载状态量目录…</p>}
                    {components.map((comp) => {
                        const isOpen = !collapsed[comp.component];
                        const compFilled = comp.items.filter((it) => {
                            const v = values[it.key];
                            return v !== undefined && v !== '' && v !== '正常';
                        }).length;
                        return (
                            <div key={comp.component} className="rounded-xl border border-white/5 bg-white/[0.02] overflow-hidden">
                                <button
                                    onClick={() => setCollapsed((p) => ({ ...p, [comp.component]: isOpen }))}
                                    className="w-full flex items-center px-4 py-2.5 text-sm font-medium text-gray-200 hover:bg-white/5"
                                >
                                    {isOpen ? <ChevronDown className="w-4 h-4 mr-2 text-cyan-400" /> : <ChevronRight className="w-4 h-4 mr-2 text-gray-500" />}
                                    {comp.component}
                                    <span className="ml-2 text-xs text-gray-500">{comp.items.length} 项</span>
                                    {compFilled > 0 && <span className="ml-2 text-[10px] px-1.5 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/20">已填 {compFilled}</span>}
                                </button>
                                {isOpen && (
                                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-x-4 gap-y-1 px-4 pb-3">
                                        {comp.items.map((it) => (
                                            <ItemRow
                                                key={it.key}
                                                item={it}
                                                value={values[it.key] ?? ''}
                                                onChange={(v) => setVal(it.key, v)}
                                            />
                                        ))}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* ============ Results ============ */}
            <div className="w-[26rem] flex-shrink-0 flex flex-col gap-4 overflow-y-auto custom-scrollbar">
                <ResultPanel evalRes={evalRes} diagRes={diagRes} busy={busy} />
            </div>
        </div>
    );
}

function ToolButton({
    onClick, children, icon, busy, disabled, tone, title,
}: {
    onClick: () => void; children: React.ReactNode; icon: React.ReactNode;
    busy?: boolean; disabled?: boolean; tone: 'cyan' | 'violet' | 'slate'; title?: string;
}) {
    const tones = {
        cyan: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30 hover:bg-cyan-500/25',
        violet: 'bg-violet-500/15 text-violet-300 border-violet-500/30 hover:bg-violet-500/25',
        slate: 'bg-white/5 text-gray-300 border-white/10 hover:bg-white/10',
    }[tone];
    return (
        <button
            onClick={onClick}
            disabled={disabled}
            title={title}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors disabled:opacity-40 ${tones}`}
        >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : icon}
            {children}
        </button>
    );
}

function ItemRow({
    item, value, onChange,
}: {
    item: DltCatalogue['components'][0]['items'][0];
    value: string | number;
    onChange: (v: string) => void;
}) {
    const active = value !== '' && value !== '正常' && value != null;
    return (
        <div className="flex items-center gap-2 py-1 group" title={item.hint}>
            <span className={`text-xs flex-1 min-w-0 truncate ${active ? 'text-gray-100' : 'text-gray-400'}`}>
                {item.name}
                {item.group && <span className="ml-1 text-[9px] text-gray-600">◦组</span>}
            </span>
            {item.input === 'qualitative' ? (
                <select
                    value={String(value) || '正常'}
                    onChange={(e) => onChange(e.target.value)}
                    className={`w-24 flex-shrink-0 bg-white/5 border rounded-md px-2 py-1 text-xs focus:outline-none focus:border-cyan-500/50 ${active ? 'border-cyan-500/40 text-cyan-200' : 'border-white/10 text-gray-400'}`}
                >
                    <option value="正常" className="bg-[#0A0B10]">正常</option>
                    {item.levels.map((lv) => (
                        <option key={lv} value={lv} className="bg-[#0A0B10]">{lv} 级</option>
                    ))}
                </select>
            ) : (
                <input
                    type="number"
                    value={value === '正常' ? '' : String(value)}
                    onChange={(e) => onChange(e.target.value)}
                    placeholder="实测值"
                    className={`w-24 flex-shrink-0 bg-white/5 border rounded-md px-2 py-1 text-xs focus:outline-none focus:border-cyan-500/50 ${active ? 'border-cyan-500/40 text-cyan-200' : 'border-white/10 text-gray-500'}`}
                />
            )}
        </div>
    );
}

function ResultPanel({
    evalRes, diagRes, busy,
}: {
    evalRes: DltEvalResult | null;
    diagRes: DltDiagnoseResult | null;
    busy: string;
}) {
    if (busy === 'diag') {
        return (
            <div className="glass-panel rounded-2xl p-6 text-sm text-gray-400 flex items-center">
                <Loader2 className="w-4 h-4 mr-2 animate-spin text-violet-400" /> 正在运行完整诊断（三源识别 → 融合 → RUL），约 30-60 秒…
            </div>
        );
    }
    if (!evalRes && !diagRes) {
        return (
            <div className="glass-panel rounded-2xl p-6 text-sm text-gray-500 leading-relaxed">
                <ShieldCheck className="w-5 h-5 text-cyan-400 mb-2" />
                录入可获取的状态量后点击<span className="text-cyan-300">「计算评分」</span>得到 DL/T 1685
                部件/整体状态；点击<span className="text-violet-300">「完整诊断」</span>进一步运行三源缺陷识别与剩余寿命预测。
                未填写的状态量按标准第 6e 条不予扣分。
            </div>
        );
    }
    return (
        <>
            {evalRes && <EvalResultCard evalRes={evalRes} />}
            {diagRes && <DiagnoseCard diagRes={diagRes} />}
        </>
    );
}

function EvalResultCard({ evalRes }: { evalRes: DltEvalResult }) {
    const st = stateStyle(evalRes.overall_state);
    const comps = Object.entries(evalRes.components);
    return (
        <div className="glass-panel rounded-2xl p-4">
            <div className="flex items-center mb-3">
                <ShieldCheck className="w-4 h-4 mr-2 text-cyan-400" />
                <span className="text-sm font-medium text-cyan-400">DL/T 1685 状态评价</span>
            </div>

            <div className={`flex items-center justify-between rounded-xl px-4 py-3 border ${st.bg} ${st.ring}`}>
                <div className="flex items-center">
                    <span className={`w-2.5 h-2.5 rounded-full mr-2 ${st.dot}`} />
                    <span className="text-xs text-gray-400 mr-2">整体状态</span>
                    <span className={`text-lg font-bold ${st.text}`}>{evalRes.overall_state}</span>
                </div>
                <div className="text-right">
                    <div className="text-2xl font-bold text-gray-100">{evalRes.health_index}</div>
                    <div className="text-[10px] text-gray-500">健康指数 (工程外延)</div>
                </div>
            </div>
            <div className="text-[10px] text-gray-600 mt-1.5 text-right">合计扣分 {evalRes.total_deduction}</div>

            <div className="mt-3 space-y-2">
                {comps.map(([name, r]) => {
                    const cs = stateStyle(r.state);
                    return (
                        <div key={name} className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2">
                            <div className="flex items-center text-xs">
                                <span className={`w-2 h-2 rounded-full mr-2 ${cs.dot}`} />
                                <span className="text-gray-200">{name}</span>
                                <span className={`ml-2 ${cs.text}`}>{r.state}</span>
                                <span className="ml-auto text-gray-500 font-mono">
                                    扣分 {r.total_deduction} · 单项峰值 {r.max_single}
                                </span>
                            </div>
                            {r.items.length > 0 && (
                                <ul className="mt-1.5 space-y-0.5">
                                    {r.items.map((it, i) => (
                                        <li key={i} className="text-[11px] text-gray-500 flex items-start">
                                            <span className="text-gray-400 mr-1.5">·</span>
                                            <span className="text-gray-300">{it.item}</span>
                                            {it.level && <span className="ml-1 text-amber-400/80">{it.level}级</span>}
                                            <span className="ml-1 text-gray-500">扣{it.deduction}</span>
                                            <span className="ml-1.5 text-gray-600 truncate">— {it.basis}</span>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

function DiagnoseCard({ diagRes }: { diagRes: DltDiagnoseResult }) {
    return (
        <div className="glass-panel rounded-2xl p-4">
            <div className="flex items-center mb-3">
                <Activity className="w-4 h-4 mr-2 text-violet-400" />
                <span className="text-sm font-medium text-violet-400">完整诊断结果</span>
            </div>
            <div className="grid grid-cols-2 gap-2 mb-3">
                <Metric label="健康指数" value={diagRes.health_index} />
                <Metric label="剩余寿命 (年)" value={diagRes.predicted_rul_years} />
                <Metric label="缺陷识别" value={diagRes.fusion_verdict_cn} sub={`置信 ${(diagRes.fusion_confidence * 100).toFixed(0)}%`} />
                <Metric label="DGA 风险" value={diagRes.dga_risk_score ?? '—'} sub={diagRes.primary_threat || ''} />
            </div>
            {diagRes.forced_override && (
                <div className="mb-3 text-[11px] text-amber-300 bg-amber-500/5 border border-amber-500/20 rounded-lg px-3 py-2">
                    ⚠ {diagRes.forced_override}
                </div>
            )}
            <details className="text-xs">
                <summary className="cursor-pointer text-gray-400 hover:text-gray-200 select-none">完整报告</summary>
                <div className="md-body mt-2 max-h-96 overflow-y-auto custom-scrollbar pr-1">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{diagRes.final_report}</ReactMarkdown>
                </div>
            </details>
        </div>
    );
}

function Metric({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
    return (
        <div className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2">
            <div className="text-[10px] text-gray-500">{label}</div>
            <div className="text-base font-bold text-gray-100 truncate">{value}</div>
            {sub && <div className="text-[10px] text-gray-500 truncate">{sub}</div>}
        </div>
    );
}
