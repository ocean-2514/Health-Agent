import React, { useEffect, useMemo, useState } from 'react';
import {
    Eye, FlaskConical, Thermometer, Waves, Activity, Info,
    TrendingUp, TrendingDown, Minus, Gauge, type LucideIcon,
} from 'lucide-react';
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { deviceModalities, type DeviceModalities } from '../lib/api';

type ModalityId = 'visible' | 'dga' | 'ir' | 'pd' | 'vib' | 'load';

type Props = {
    health: any;
    defect: any;
    deviceId?: string;
    isSample?: boolean;
};

const GAS_LABELS: Record<string, string> = {
    H2: 'H2 氢气',
    CH4: 'CH4 甲烷',
    C2H6: 'C2H6 乙烷',
    C2H4: 'C2H4 乙烯',
    C2H2: 'C2H2 乙炔',
    CO: 'CO 一氧化碳',
    CO2: 'CO2 二氧化碳',
};
const GAS_ORDER = ['H2', 'CH4', 'C2H6', 'C2H4', 'C2H2', 'CO', 'CO2'];

const SOURCE_LABELS: Record<string, string> = {
    yolo: '图像检查',
    bert: '巡检记录',
    cnn: '油色谱分析',
};

const STATUS_CLS: Record<string, string> = {
    '正常': 'bg-[#eef7e8] text-[#5ba83c] border-[#aed894]',
    '关注': 'bg-[#fbeed2] text-[#d99000] border-[#e8cd92]',
    '异常': 'bg-[#fbe3d4] text-[#ff5b01] border-[#f0ac84]',
};

function fmtNum(v: any): string {
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(2) : '—';
}

function trendOf(values?: number[]): { dir: 'up' | 'down' | 'flat'; text: string } {
    if (!values || values.length < 2) return { dir: 'flat', text: '样本不足' };
    const first = values[0];
    const last = values[values.length - 1];
    if (Math.abs(last - first) < Math.max(Math.abs(first) * 0.05, 0.1)) {
        return { dir: 'flat', text: '基本平稳' };
    }
    return last > first ? { dir: 'up', text: '区间上升' } : { dir: 'down', text: '区间下降' };
}

export default function ModalityFusion({ health, defect, deviceId, isSample }: Props) {
    const [active, setActive] = useState<ModalityId>('visible');
    const [modals, setModals] = useState<DeviceModalities | null>(null);

    useEffect(() => {
        let alive = true;
        deviceModalities(deviceId ?? 'tr01').then((r) => { if (alive) setModals(r); });
        return () => { alive = false; };
    }, [deviceId]);

    const hasImage = Boolean(defect?.source_evidence?.image_url);
    const dgaData = health?.dga_data ?? {};

    const modalities: { id: ModalityId; label: string; icon: LucideIcon; status?: string }[] = [
        { id: 'visible', label: '图像检查', icon: Eye, status: hasImage ? '正常' : undefined },
        { id: 'dga', label: '油色谱', icon: FlaskConical, status: dgaData ? '正常' : undefined },
        { id: 'ir', label: '红外测温', icon: Thermometer, status: modals?.ir?.overall_status },
        { id: 'pd', label: '局放检测', icon: Waves, status: modals?.pd?.overall_status },
        { id: 'vib', label: '振动分析', icon: Activity, status: modals?.vib?.overall_status },
        { id: 'load', label: '温度负载', icon: Gauge, status: modals?.temp_load?.overall_status || (modals?.temp_load?.condition === 'warning' ? '关注' : '正常') },
    ];

    return (
        <div className="glass-panel rounded-xl p-5 flex flex-col">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <div className="flex items-center text-[#209F84]">
                    <Eye className="w-4 h-4 mr-2" />
                    <span className="text-sm font-bold uppercase tracking-wider">多源检查视图</span>
                </div>
                {isSample && modals?.data_source && (
                    <span className="text-[10px] text-[#d99000]">{modals.data_source.label}</span>
                )}
            </div>

            <div className="flex items-center gap-2 flex-wrap mb-4">
                {modalities.map((m) => {
                    const Icon = m.icon;
                    const selected = active === m.id;
                    return (
                        <button
                            key={m.id}
                            onClick={() => setActive(m.id)}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs transition-colors ${
                                selected
                                    ? 'bg-[#e6f4f0] text-[#209F84] border-[#7fc4b8]'
                                    : 'bg-[#f8f8fa] text-[#666666] border-[#dcdfe6] hover:bg-[#f2f4f6]'
                            }`}
                        >
                            <Icon className="w-3.5 h-3.5" />
                            {m.label}
                            {m.status && (
                                <span className={`text-[9px] px-1.5 py-0.5 rounded border ${STATUS_CLS[m.status] ?? STATUS_CLS['正常']}`}>
                                    {m.status}
                                </span>
                            )}
                        </button>
                    );
                })}
            </div>

            <div className="flex-1 min-h-[300px]">
                {active === 'visible' && <VisiblePanel defect={defect} />}
                {active === 'dga' && <DgaPanel dgaData={dgaData} health={health} />}
                {active === 'ir' && <IrPanel sample={modals?.ir} />}
                {active === 'pd' && <PdPanel sample={modals?.pd} />}
                {active === 'vib' && <VibPanel sample={modals?.vib} />}
                {active === 'load' && <LoadPanel sample={modals?.temp_load} />}
            </div>
        </div>
    );
}

function VisiblePanel({ defect }: { defect: any }) {
    const evidence = defect?.source_evidence || {};
    const textSources = ['yolo', 'bert', 'cnn'] as const;

    return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="relative h-56 rounded-lg overflow-hidden bg-black/30 border border-[#dcdfe6] flex items-center justify-center">
                {evidence.image_url ? (
                    <img src={evidence.image_url} alt="巡检参考图像" className="w-full h-full object-cover opacity-80" />
                ) : (
                    <div className="text-center text-[#666666] text-xs">暂无巡检参考图像</div>
                )}
                <div className="absolute top-2 left-2 px-2 py-1 rounded-full text-[9px] border bg-[#fbeed2] text-[#d99000] border-[#e8cd92]">
                    巡检参考图（标准样本）
                </div>
            </div>

            <div className="space-y-2.5">
                {textSources.map((key) => (
                    <div key={key} className="rounded-lg border border-[#dcdfe6] bg-[#f8f8fa] px-3 py-2">
                        <div className="flex items-center justify-between mb-1">
                            <span className="text-[10px] text-[#209F84] font-bold">{SOURCE_LABELS[key]}</span>
                            <span className="text-[9px] px-1.5 py-0.5 rounded border bg-[#fdf4e0] text-[#d99000] border-[#f0d9a8]">
                                标准样本
                            </span>
                        </div>
                        <p className="text-[11px] text-[#333333] leading-relaxed">{evidence[key] || '暂无该来源结论。'}</p>
                    </div>
                ))}
                <p className="text-[10px] text-[#666666] leading-relaxed flex items-start">
                    <Info className="w-3 h-3 mr-1 mt-0.5 flex-shrink-0" />
                    接入现场抓拍后，本区域将自动展示图像识别结果。
                </p>
            </div>
        </div>
    );
}

function IrPanel({ sample }: { sample: any }) {
    const data = useMemo(() => {
        const series = sample?.oil_top_temp_series;
        if (!series) return [];
        return series.labels.map((l: string, i: number) => ({ t: l, 顶层油温: series.values[i] }));
    }, [sample]);

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-3 gap-2">
                <Metric label="环境温度" value={sample?.ambient_c != null ? `${sample.ambient_c} ℃` : '—'} />
                <Metric label="最高热点温度" value={sample?.max_hotspot?.temp_c != null ? `${sample.max_hotspot.temp_c} ℃` : '—'} sub={sample?.max_hotspot?.part} />
                <Metric label="热点温差" value={sample?.max_hotspot?.delta_k != null ? `${sample.max_hotspot.delta_k} K` : '—'} sub="热点与环境温差" />
            </div>
            <div className="rounded-lg border border-[#dcdfe6] bg-[#f8f8fa] p-3">
                <div className="text-[11px] text-[#209F84] font-bold mb-2">部件热点清单</div>
                <div className="space-y-1.5">
                    {(sample?.hotspots ?? []).map((h: any) => (
                        <div key={h.part} className="flex items-center text-xs">
                            <span className="w-24 text-[#333333]">{h.part}</span>
                            <span className="flex-1 font-mono text-[#333333]">{h.temp_c} ℃</span>
                            <span className="text-[#666666] text-[11px] mr-3">温差 {h.delta_k} K</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${STATUS_CLS[h.status] ?? STATUS_CLS['正常']}`}>{h.status}</span>
                        </div>
                    ))}
                </div>
            </div>
            <div>
                <div className="text-[11px] text-[#209F84] font-bold mb-2">近 24 小时顶层油温趋势</div>
                <div className="h-[150px]">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={data}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#ebeef5" vertical={false} />
                            <XAxis dataKey="t" stroke="#666666" fontSize={9} tickLine={false} axisLine={false} />
                            <YAxis stroke="#666666" fontSize={9} tickLine={false} axisLine={false} />
                            <Tooltip contentStyle={{ backgroundColor: '#ffffff', border: '1px solid #dcdfe6', borderRadius: 8, color: '#333333' }} />
                            <Line type="monotone" dataKey="顶层油温" stroke="#209F84" strokeWidth={1.5} dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
}

function PdPanel({ sample }: { sample: any }) {
    const data = useMemo(() => {
        const s = sample?.pulse_series;
        if (!s) return [];
        return s.labels.map((l: string, i: number) => ({ t: l, 放电量: s.values[i] }));
    }, [sample]);
    const phases = Object.entries(sample?.phase_counts ?? {});
    const maxCount = Math.max(1, ...phases.map(([, v]) => v as number));

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-3 gap-2">
                <Metric label="最大放电量" value={sample?.max_pulse_pc != null ? `${sample.max_pulse_pc} pC` : '—'} />
                <Metric label="总体状态" value={sample?.overall_status ?? '—'} />
                <Metric label="判据参考" value="DL/T 722" sub={sample?.baseline_note} small />
            </div>
            <div>
                <div className="text-[11px] text-[#209F84] font-bold mb-2">放电幅值趋势（pC）</div>
                <div className="h-[150px]">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={data}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#ebeef5" vertical={false} />
                            <XAxis dataKey="t" stroke="#666666" fontSize={9} tickLine={false} axisLine={false} />
                            <YAxis stroke="#666666" fontSize={9} tickLine={false} axisLine={false} />
                            <Tooltip contentStyle={{ backgroundColor: '#ffffff', border: '1px solid #dcdfe6', borderRadius: 8, color: '#333333' }} />
                            <Line type="monotone" dataKey="放电量" stroke="#FCAA00" strokeWidth={1.5} dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>
            <div className="rounded-lg border border-[#dcdfe6] bg-[#f8f8fa] p-3">
                <div className="text-[11px] text-[#209F84] font-bold mb-2">分相放电脉冲计数</div>
                <div className="space-y-2">
                    {phases.map(([k, v]) => (
                        <div key={k} className="flex items-center text-xs gap-2">
                            <span className="w-12 text-[#333333]">{k}</span>
                            <div className="flex-1 h-2 rounded-full bg-[#f8f8fa] overflow-hidden">
                                <div className="h-full bg-[#fcaa00]" style={{ width: `${((v as number) / maxCount) * 100}%` }} />
                            </div>
                            <span className="font-mono text-[#333333] w-16 text-right">{Number(v)} 次</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

function VibPanel({ sample }: { sample: any }) {
    const spec = sample?.spectrum;
    const maxSpec = Math.max(1, ...(spec?.values ?? [1]));
    return (
        <div className="space-y-4">
            <div className="rounded-lg border border-[#dcdfe6] bg-[#f8f8fa] p-3">
                <div className="text-[11px] text-[#209F84] font-bold mb-2">测点振动速度（mm/s）</div>
                <div className="space-y-2">
                    {(sample?.positions ?? []).map((p: any) => (
                        <div key={p.part} className="flex items-center text-xs gap-2">
                            <span className="w-24 text-[#333333]">{p.part}</span>
                            <span className="font-mono text-[#333333] w-16">{p.velocity_mms}</span>
                            <span className="flex-1 text-[#666666] text-[10px]">注意值 {p.warn_mms}</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${STATUS_CLS[p.status] ?? STATUS_CLS['正常']}`}>{p.status}</span>
                        </div>
                    ))}
                </div>
            </div>
            <div className="rounded-lg border border-[#dcdfe6] bg-[#f8f8fa] p-3">
                <div className="text-[11px] text-[#209F84] font-bold mb-2">频谱峰值分布</div>
                <div className="flex items-end gap-2 h-[140px]">
                    {(spec?.labels ?? []).map((label: string, i: number) => (
                        <div key={label} className="flex-1 flex flex-col items-center gap-1">
                            <div className="w-full rounded-t bg-[#c5e4dc]" style={{ height: `${((spec.values[i] ?? 0) / maxSpec) * 100}%` }} />
                            <span className="text-[9px] text-[#666666]">{label}</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

function LoadPanel({ sample }: { sample: any }) {
    const chartData = useMemo(() => {
        const labels: string[] = sample?.oil_top_temp?.labels || [];
        return labels.map((label, i) => ({
            t: label,
            顶层油温: sample?.oil_top_temp?.values?.[i],
            负载率: sample?.load_rate?.values?.[i] != null
                ? Number((sample.load_rate.values[i] * 100).toFixed(1))
                : undefined,
        }));
    }, [sample]);
    const temps: number[] = sample?.oil_top_temp?.values || [];
    const loads: number[] = sample?.load_rate?.values || [];
    const status = sample?.condition === 'warning' ? '关注' : '正常';

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-3 gap-2">
                <Metric label="最高顶层油温" value={temps.length ? `${Math.max(...temps).toFixed(1)} ℃` : '—'} />
                <Metric label="最高负载率" value={loads.length ? `${(Math.max(...loads) * 100).toFixed(1)}%` : '—'} />
                <Metric label="运行提示" value={status} sub={status === '关注' ? '温度与负载偏高，建议跟踪' : '处于常规区间'} small />
            </div>
            <div className="rounded-lg border border-[#dcdfe6] bg-[#f8f8fa] p-3">
                <div className="text-[11px] text-[#209F84] font-bold mb-2">顶层油温与负载率趋势</div>
                <div className="h-[220px]">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#ebeef5" vertical={false} />
                            <XAxis dataKey="t" stroke="#666666" fontSize={9} tickLine={false} axisLine={false} />
                            <YAxis stroke="#666666" fontSize={9} tickLine={false} axisLine={false} />
                            <Tooltip contentStyle={{ backgroundColor: '#ffffff', border: '1px solid #dcdfe6', borderRadius: 8, color: '#333333' }} />
                            <Line type="monotone" dataKey="顶层油温" stroke="#FCAA00" strokeWidth={1.5} dot={false} />
                            <Line type="monotone" dataKey="负载率" stroke="#209F84" strokeWidth={1.5} dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>
            <p className="text-[10px] text-[#666666] leading-relaxed">温度与负载序列来自标准样本，用于观察工况变化；接入在线监测后按实测值更新并自动触发越限提示。</p>
        </div>
    );
}

function DgaPanel({ dgaData, health }: { dgaData: Record<string, any>; health: any }) {
    const riskCurve = health?.fault_risk_curve;
    const riskData = useMemo(() => {
        if (!riskCurve?.x || !riskCurve?.y) return [];
        return riskCurve.x.map((x: number, i: number) => ({ name: x, risk: riskCurve.y[i] }));
    }, [riskCurve]);

    const rows = GAS_ORDER.filter((k) => dgaData[k]).map((k) => {
        const trend = trendOf(dgaData[k]?.values);
        return {
            key: k, label: GAS_LABELS[k],
            latest: fmtNum(dgaData[k]?.values?.slice(-1)[0]),
            ts: dgaData[k]?.timestamps?.slice(-1)[0] || '—',
            count: Array.isArray(dgaData[k]?.values) ? dgaData[k].values.length : 0,
            trend,
        };
    });

    const breakdown: { type: string; probability: number }[] = Array.isArray(health?.fault_breakdown) ? health.fault_breakdown : [];

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-3 gap-2">
                <Metric label="综合风险评分" value={health?.risk_score != null ? `${Number(health.risk_score).toFixed(1)}` : '—'} sub="0-100" />
                <Metric label="主要威胁" value={health?.primary_threat || '—'} sub="油色谱联动分析" small />
                <Metric label="气体测点数" value={String(rows.length)} sub={`共 ${rows.reduce((s, r) => s + r.count, 0)} 个采样点`} />
            </div>

            <div className="rounded-lg border border-[#dcdfe6] bg-[#f8f8fa] overflow-hidden">
                <table className="w-full text-left">
                    <thead className="text-[10px] text-[#666666] uppercase border-b border-[#dcdfe6]">
                        <tr>
                            <th className="py-2 px-3 font-medium">气体组分</th>
                            <th className="py-2 px-3 font-medium">最新值 (µL/L)</th>
                            <th className="py-2 px-3 font-medium">采样时刻</th>
                            <th className="py-2 px-3 font-medium">区间趋势</th>
                        </tr>
                    </thead>
                    <tbody className="text-xs">
                        {rows.map((r) => (
                            <tr key={r.key} className="border-b border-[#dcdfe6] last:border-0">
                                <td className="py-2 px-3 text-[#333333] font-medium">{r.label}</td>
                                <td className="py-2 px-3 text-[#333333] font-mono">{r.latest}</td>
                                <td className="py-2 px-3 text-[#666666] font-mono text-[10px]">{r.ts}</td>
                                <td className="py-2 px-3">
                                    <span className="inline-flex items-center text-[11px] text-[#666666]">
                                        {r.trend.dir === 'up' && <TrendingUp className="w-3 h-3 mr-1 text-[#d99000]" />}
                                        {r.trend.dir === 'down' && <TrendingDown className="w-3 h-3 mr-1 text-[#3d8fe8]" />}
                                        {r.trend.dir === 'flat' && <Minus className="w-3 h-3 mr-1 text-[#666666]" />}
                                        {r.trend.text} · {r.count} 点
                                    </span>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div>
                    <div className="text-[11px] text-[#209F84] font-bold mb-2">故障分项概率</div>
                    <div className="space-y-2">
                        {breakdown.length === 0 && <p className="text-[11px] text-[#666666]">暂无故障分项结果。</p>}
                        {breakdown.map((b) => (
                            <div key={b.type}>
                                <div className="flex justify-between text-[11px] mb-1">
                                    <span className="text-[#333333]">{b.type}</span>
                                    <span className="text-[#666666] font-mono">{Number(b.probability).toFixed(1)}%</span>
                                </div>
                                <div className="w-full bg-[#f8f8fa] h-1.5 rounded-full overflow-hidden">
                                    <div className="h-full bg-[#209F84]" style={{ width: `${Math.min(100, Number(b.probability))}%` }} />
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
                <div>
                    <div className="text-[11px] text-[#209F84] font-bold mb-2">风险演化趋势（未来年份）</div>
                    <div className="h-[140px]">
                        {riskData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={riskData}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#ebeef5" vertical={false} />
                                    <XAxis dataKey="name" stroke="#666666" fontSize={9} tickLine={false} axisLine={false} />
                                    <YAxis stroke="#666666" fontSize={9} tickLine={false} axisLine={false} domain={[0, 100]} />
                                    <Tooltip contentStyle={{ backgroundColor: '#ffffff', border: '1px solid #dcdfe6', borderRadius: 8, color: '#333333' }} />
                                    <Line type="monotone" dataKey="risk" stroke="#FCAA00" strokeWidth={1.5} dot={{ fill: '#FCAA00', r: 2 }} />
                                </LineChart>
                            </ResponsiveContainer>
                        ) : <p className="text-[11px] text-[#666666]">暂无风险曲线数据。</p>}
                    </div>
                </div>
            </div>

            <p className="text-[10px] text-[#666666] leading-relaxed">气体数值来自标准样本序列，供趋势研判参考；接入在线油化监测后展示实时测点值并按 DL/T 722 自动判级。</p>
        </div>
    );
}

function Metric({ label, value, sub, small }: { label: string; value: string; sub?: string; small?: boolean }) {
    return (
        <div className="rounded-lg border border-[#dcdfe6] bg-[#f8f8fa] px-3 py-2">
            <div className="text-[10px] text-[#666666]">{label}</div>
            <div className={`font-bold text-[#333333] ${small ? 'text-sm' : 'text-lg'}`}>{value}</div>
            {sub && <div className="text-[9px] text-[#666666] truncate">{sub}</div>}
        </div>
    );
}

