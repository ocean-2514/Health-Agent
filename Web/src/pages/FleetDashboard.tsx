import React, { useEffect, useMemo, useState } from 'react';
import HealthRadar from '../components/RadarChart';
import DeviceTree from '../components/DeviceTree';
import WarningFlow from '../components/WarningFlow';
import {
    ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts';
import {
    CheckCircle2, AlertTriangle, XCircle, Activity, Wrench, FileCheck2,
    RefreshCw, ArrowRight, ClipboardList, Gauge, ShieldAlert,
} from 'lucide-react';
import { useData } from '../lib/store';
import { fleetDatasetManifest, type FleetDevice, type DatasetManifest } from '../lib/api';

const STATUS_META: Record<string, { label: string; cls: string; dot: string; icon: React.ReactNode }> = {
    '正常': { label: '运行平稳', cls: 'bg-[#eef7e8] text-[#5ba83c] border-[#aed894]', dot: 'bg-[#6fba47]', icon: <CheckCircle2 className="w-4 h-4 text-[#5ba83c]" /> },
    '关注': { label: '需关注', cls: 'bg-[#fbeed2] text-[#d99000] border-[#e8cd92]', dot: 'bg-[#fcaa00]', icon: <AlertTriangle className="w-4 h-4 text-[#d99000]" /> },
    '异常': { label: '异常观察', cls: 'bg-orange-500/15 text-[#f07a1a] border-[#f3c39c]', dot: 'bg-[#f58a3a]', icon: <AlertTriangle className="w-4 h-4 text-[#f07a1a]" /> },
    '严重': { label: '严重告警', cls: 'bg-[#fbe3d4] text-[#ff5b01] border-[#f0ac84]', dot: 'bg-red-500', icon: <XCircle className="w-4 h-4 text-[#ff5b01]" /> },
};

const orderStatusCls = (s: string) => ({
    '待派单': 'bg-[#fbeed2] text-[#d99000]',
    '已派单': 'bg-[#dcecfd] text-[#3d8fe8]',
    '处理中': 'bg-[#ece2fc] text-[#8a63e0]',
    '已闭环': 'bg-[#eef7e8] text-[#5ba83c]',
}[s] || 'bg-[#f2f4f6] text-[#333333]');

export default function FleetDashboard(_props: { onNavigateToAI?: (id: string) => void }) {
    const {
        overview, overviewLoading, refreshOverview,
        workorders, openOrderCount, issuedCount, refreshWorkorders,
        navigate,
    } = useData();
    const [stationId, setStationId] = useState('station1');
    const [manifest, setManifest] = useState<DatasetManifest | null>(null);

    useEffect(() => {
        fleetDatasetManifest().then(setManifest);
    }, []);

    const currentStation = useMemo(
        () => overview?.stations.find((s) => s.id === stationId) ?? overview?.stations[0],
        [overview, stationId],
    );

    const radarData = useMemo(() => {
        const devices = currentStation?.devices ?? [];
        if (!devices.length) return [];
        const avg = (fn: (d: FleetDevice) => number) =>
            devices.reduce((sum, d) => sum + fn(d), 0) / devices.length;
        return [
            { subject: '健康水平', A: Math.round(avg((d) => d.health_index)) },
            { subject: '油色谱', A: Math.round(Math.max(35, Math.min(100, 100 - avg((d) => d.risk_score) * 2))) },
            { subject: '绝缘状态', A: Math.round(Math.max(40, avg((d) => d.health_index) - 6)) },
            { subject: '运行负载', A: 82 },
            { subject: '剩余寿命', A: Math.round(Math.max(20, Math.min(100, avg((d) => d.rul_years) * 4))) },
            { subject: '检修准备', A: Math.max(30, Math.min(100, 100 - avg((d) => d.open_orders) * 15)) },
        ];
    }, [currentStation]);

    const trendData = useMemo(() => {
        const c = overview?.fleet_risk_curve;
        if (!c || !c.x?.length) return [];
        return c.x.map((x, i) => ({ year: String(x), 风险评分: c.y[i] ?? 0 }));
    }, [overview]);

    const counts = overview?.summary.status_counts ?? {};
    const kpis = [
        { label: '在运变压器', value: overview?.summary.device_total ?? 0, sub: '覆盖两座变电站', icon: <Gauge className="w-5 h-5 text-[#209F84]" /> },
        { label: '平均健康指数', value: overview?.summary.avg_hi ?? '—', sub: '越高代表状态越好', icon: <Activity className="w-5 h-5 text-[#5ba83c]" /> },
        { label: '关注 / 异常设备', value: (counts['关注'] ?? 0) + (counts['异常'] ?? 0) + (counts['严重'] ?? 0), sub: '建议优先复核与安排试验', icon: <ShieldAlert className="w-5 h-5 text-[#d99000]" /> },
        { label: '待办检修工单', value: openOrderCount, sub: `已签发复核意见 ${issuedCount} 份`, icon: <ClipboardList className="w-5 h-5 text-[#8a63e0]" /> },
    ];

    return (
        <div className="flex min-h-full space-x-4">
            <div className="w-64 glass-panel rounded-xl overflow-hidden flex-shrink-0">
                <DeviceTree />
            </div>

            <div className="flex-1 flex flex-col space-y-4 min-w-0">
                {/* Page header */}
                <div className="glass-panel rounded-xl px-5 py-4 flex items-center justify-between">
                    <div>
                        <h2 className="text-lg font-bold text-[#333333]">综合评估 · 设备健康态势总览</h2>
                        <p className="text-xs text-[#666666] mt-1">
                            {overview ? `数据生成时间 ${overview.generated_at}` : '正在汇总各分析页面结果'}
                            {overview && <span className="text-[#d99000]"> · {overview.data_source.label}</span>}
                        </p>
                    </div>
                    <button
                        onClick={async () => { await refreshOverview(); await refreshWorkorders(); }}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#e6f4f0] border border-[#9cd2c7] text-[#209F84] text-xs hover:bg-[#dceee9] transition-colors"
                    >
                        <RefreshCw className={`w-3.5 h-3.5 ${overviewLoading ? 'animate-spin' : ''}`} />
                        刷新汇总
                    </button>
                </div>

                {overviewLoading && (
                    <div className="glass-panel rounded-xl p-10 text-center text-[#666666] text-sm animate-pulse">
                        正在汇总健康指数、标准评价、告警与工单结果…
                    </div>
                )}
                {!overviewLoading && !overview && (
                    <div className="glass-panel rounded-xl p-10 text-center space-y-3">
                        <p className="text-[#333333] text-sm">设备概览数据暂时无法加载。</p>
                        <button onClick={refreshOverview} className="px-4 py-1.5 rounded-lg bg-[#e6f4f0] text-[#209F84] text-xs border border-[#9cd2c7]">
                            重新加载
                        </button>
                    </div>
                )}

                {overview && (
                    <>
                        {/* KPI row */}
                        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
                            {kpis.map((k) => (
                                <div key={k.label} className="glass-panel rounded-xl p-4">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-xs text-[#666666]">{k.label}</span>
                                        {k.icon}
                                    </div>
                                    <div className="text-3xl font-bold text-[#333333] tabular-nums">{k.value}</div>
                                    <div className="text-[11px] text-[#666666] mt-1">{k.sub}</div>
                                </div>
                            ))}
                        </div>

                        {/* Radar + trend */}
                        <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
                            <div className="xl:col-span-3 glass-panel rounded-xl p-5">
                                <div className="flex items-center justify-between mb-2">
                                    <div>
                                        <h3 className="text-sm font-semibold text-[#333333]">
                                            {currentStation?.name ?? '本站'} · 健康能力画像
                                        </h3>
                                        <p className="text-[11px] text-[#666666] mt-0.5">由各设备健康指数、油色谱趋势与剩余寿命综合折算</p>
                                    </div>
                                    <select
                                        value={stationId}
                                        onChange={(e) => setStationId(e.target.value)}
                                        className="bg-[#f8f8fa] border border-[#dcdfe6] rounded-lg text-xs text-[#333333] px-2 py-1.5 focus:outline-none"
                                    >
                                        {overview.stations.map((s) => (
                                            <option key={s.id} value={s.id}>{s.name}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="h-72">
                                    <HealthRadar data={radarData} />
                                </div>
                            </div>

                            <div className="xl:col-span-2 glass-panel rounded-xl p-5">
                                <h3 className="text-sm font-semibold text-[#333333] mb-1">全网风险演化趋势（未来 8 年）</h3>
                                <p className="text-[11px] text-[#666666] mb-2">依据油色谱残差与劣化趋势外推测算，供趋势研判参考</p>
                                <div className="h-72">
                                    {trendData.length ? (
                                        <ResponsiveContainer width="100%" height="100%">
                                            <LineChart data={trendData} margin={{ top: 8, right: 12, left: -18, bottom: 0 }}>
                                                <CartesianGrid stroke="#ebeef5" />
                                                <XAxis dataKey="year" tick={{ fill: '#666666', fontSize: 11 }} />
                                                <YAxis tick={{ fill: '#666666', fontSize: 11 }} domain={[0, 100]} />
                                                <Tooltip contentStyle={{ background: '#ffffff', border: '1px solid #dcdfe6', borderRadius: 8, fontSize: 12 }} />
                                                <Legend wrapperStyle={{ fontSize: 11 }} />
                                                <Line type="monotone" dataKey="风险评分" stroke="#209F84" strokeWidth={2} dot={false} />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    ) : (
                                        <div className="h-full flex items-center justify-center text-xs text-[#666666]">暂无趋势数据</div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Device cards */}
                        <div className="glass-panel rounded-xl p-5">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-sm font-semibold text-[#333333]">设备健康卡片</h3>
                                <span className="text-[11px] text-[#666666]">点击「AI分析」查看完整诊断；点击「标准评价」开展规程定级</span>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                                {overview.stations.flatMap((s) => s.devices).map((d) => {
                                    const meta = STATUS_META[d.status] ?? STATUS_META['正常'];
                                    return (
                                        <div key={d.equipment_id} className="glass-panel rounded-xl p-4 border border-[#dcdfe6] hover:border-[#b3ddd5] transition-colors">
                                            <div className="flex items-start justify-between mb-3">
                                                <div className="min-w-0">
                                                    <div className="text-sm font-semibold text-[#333333] truncate">{d.name}</div>
                                                    <div className="text-[11px] text-[#666666] truncate">{d.station_name} · {d.model}</div>
                                                </div>
                                                <span className={`text-[10px] px-2 py-0.5 rounded-full border flex-shrink-0 ${meta.cls}`}>{meta.label}</span>
                                            </div>

                                            <div className="flex items-end justify-between mb-3">
                                                <div>
                                                    <div className="text-[11px] text-[#666666]">健康指数</div>
                                                    <div className="text-3xl font-bold text-[#209F84] tabular-nums">{d.health_index}</div>
                                                </div>
                                                <div className="text-right text-[11px] text-[#666666] space-y-0.5">
                                                    <div>剩余寿命 <span className="text-[#333333] tabular-nums">{d.rul_years} 年</span></div>
                                                    <div>风险评分 <span className="text-[#333333] tabular-nums">{d.risk_score}</span></div>
                                                    <div>
                                                        DL/T 定级：
                                                        {d.dlt_state
                                                            ? <span className="text-[#d99000]">{d.dlt_state}</span>
                                                            : <span className="text-[#666666]">待评价</span>}
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-3 text-[11px] text-[#666666] mb-3">
                                                <span>红外 {d.modal_status.ir}</span>
                                                <span>局放 {d.modal_status.pd}</span>
                                                <span>振动 {d.modal_status.vib}</span>
                                                {d.open_orders > 0 && (
                                                    <span className="ml-auto text-[#8a63e0]">未闭环工单 {d.open_orders}</span>
                                                )}
                                            </div>

                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() => navigate('reasoning', { deviceId: d.equipment_id })}
                                                    className="flex-1 flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg bg-[#e6f4f0] border border-[#9cd2c7] text-[#209F84] text-xs hover:bg-[#dceee9] transition-colors"
                                                >
                                                    AI分析 <ArrowRight className="w-3 h-3" />
                                                </button>
                                                <button
                                                    onClick={() => navigate('dlt', { deviceId: d.equipment_id })}
                                                    className="flex-1 flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] text-[#333333] text-xs hover:bg-[#f2f4f6] transition-colors"
                                                >
                                                    <FileCheck2 className="w-3 h-3" /> 标准评价
                                                </button>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Workorder strip */}
                        <div className="glass-panel rounded-xl p-5">
                            <div className="flex items-center justify-between mb-3">
                                <h3 className="text-sm font-semibold text-[#333333] flex items-center gap-2">
                                    <Wrench className="w-4 h-4 text-[#8a63e0]" /> 检修工单闭环跟踪
                                </h3>
                                <button
                                    onClick={() => navigate('approval')}
                                    className="text-xs text-[#209F84] hover:text-[#209F84] flex items-center gap-1"
                                >
                                    前往专家复核 <ArrowRight className="w-3 h-3" />
                                </button>
                            </div>
                            {workorders.length === 0 ? (
                                <p className="text-xs text-[#666666] py-3">暂无工单记录；专家复核确认后可在此跟踪流转状态。</p>
                            ) : (
                                <div className="space-y-2">
                                    {workorders.slice(0, 5).map((w) => (
                                        <div key={w.order_no} className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] text-xs">
                                            <span className="font-mono text-[#666666]">{w.order_no}</span>
                                            <span className="text-[#333333] truncate">{w.equipment_name} · {w.work_type}</span>
                                            <span className="text-[#666666] hidden md:inline">{w.assignee_team}</span>
                                            <span className={`ml-auto px-2 py-0.5 rounded ${orderStatusCls(w.status)}`}>{w.status}</span>
                                            <span className="text-[#666666] tabular-nums">{w.created_at}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {manifest && (
                            <div className="glass-panel rounded-xl p-5">
                                <div className="flex items-center gap-2 mb-2">
                                    <ShieldAlert className="w-4 h-4 text-[#209F84]" />
                                    <h3 className="text-sm font-semibold text-[#333333]">样本数据来源说明</h3>
                                    <span className="ml-auto text-[10px] text-[#666666]">共 {manifest.source_count} 类标准 / 公开参考资料</span>
                                </div>
                                <p className="text-[11px] text-[#666666] leading-relaxed">
                                    本页设备画像、趋势与研判结果基于公开标准样本和确定性分析模型生成，非现场实时采集数据；样本用于演示分析流程和决策逻辑，正式状态以现场试验、巡检与在线监测实测结果为准。
                                </p>
                            </div>
                        )}
                    </>
                )}
            </div>

            <div className="w-80 glass-panel rounded-xl overflow-hidden flex-shrink-0">
                <WarningFlow onOpenAlarm={(cameraId) => navigate('monitor', { cameraId })} />
            </div>
        </div>
    );
}
