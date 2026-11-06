import React, { useEffect, useMemo, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import AIChat from '../components/AIChat';
import ModalityFusion from '../components/ModalityFusion';
import ReportWorkorder from '../components/ReportWorkorder';
import { Card, CardContent, CardHeader, CardTitle } from '../components/Card';
import { assessHealth, assessDefect, deviceLedger, deviceHistory, deviceDga, type Ledger } from '../lib/api';
import { useData } from '../lib/store';
import { Table, BarChart3, History, Info } from 'lucide-react';

// DGA 气体键与中文标签（与 ModalityFusion 视图保持一致）
const GAS_LABELS: Record<string, string> = {
    H2: 'H2 (氢气)',
    CH4: 'CH4 (甲烷)',
    C2H6: 'C2H6 (乙烷)',
    C2H4: 'C2H4 (乙烯)',
    C2H2: 'C2H2 (乙炔)',
    CO: 'CO (一氧化碳)',
    CO2: 'CO2 (二氧化碳)',
};
const GAS_ORDER = ['H2', 'CH4', 'C2H6', 'C2H4', 'C2H2', 'CO', 'CO2'];

export default function ReasoningHub({
    deviceId,
    onNavigateAgent,
}: {
    deviceId?: string;
    onNavigateAgent?: () => void;
}) {
    const { overview } = useData();
    const [data, setData] = useState<any>(null);
    const [defectData, setDefectData] = useState<any>(null);
    const [ledgerInfo, setLedgerInfo] = useState<Ledger | null>(null);
    const [history, setHistory] = useState<Array<{ date: string; type: string; result: string; operator: string }>>([]);
    const [dgaSample, setDgaSample] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        // 评估接口可能耗时较长；超时后不阻断页面，确定性样本值由统一概览层兜底。
        const withGuard = (p: Promise<any>) =>
            new Promise<any>((resolve) => {
                const timer = setTimeout(() => resolve({ __failed: true }), 40000);
                p.then((v) => { clearTimeout(timer); resolve(v); })
                    .catch(() => { clearTimeout(timer); resolve({ __failed: true }); });
            });

        Promise.all([
            withGuard(assessHealth({ id: deviceId, use_profile: true })),
            withGuard(assessDefect({ id: deviceId }))
        ]).then(([healthRes, defectRes]) => {
            if (cancelled) return;
            const healthBad = !healthRes || healthRes.__failed;
            const defectBad = !defectRes || defectRes.__failed;
            setData(healthBad ? {} : healthRes);
            setDefectData(defectBad ? {} : defectRes);
            setLoading(false);
        });

        deviceLedger(deviceId ?? 'tr01').then((r) => { if (!cancelled) setLedgerInfo(r); });
        deviceHistory(deviceId ?? 'tr01').then((r) => { if (!cancelled) setHistory(r?.records ?? []); });
        return () => { cancelled = true; };
    }, [deviceId]);

    useEffect(() => {
        let cancelled = false;
        deviceDga(deviceId ?? 'tr01').then((r) => { if (!cancelled) setDgaSample(r); });
        return () => { cancelled = true; };
    }, [deviceId]);

    const overviewDevice = useMemo(
        () => overview?.stations.flatMap((s) => s.devices).find((d) => d.equipment_id === deviceId),
        [overview, deviceId],
    );

    const curveSource = data?.health_deduction_curve?.x?.length
        ? data.health_deduction_curve
        : overviewDevice?.health_curve;
    const hiData = (curveSource?.x ?? []).map((x: number, i: number) => ({
        name: x,
        HI: curveSource.y[i],
    }));

    // 健康分与剩余寿命优先取实时评估接口；未及时返回时回退首页同源样本概览值。
    const healthIndex: number =
        typeof data?.health_index === 'number' ? data.health_index : (overviewDevice?.health_index ?? 0);
    const rul: number =
        typeof data?.predicted_rul === 'number' ? data.predicted_rul : (overviewDevice?.rul_years ?? 0);
    const riskScore: number =
        typeof data?.risk_score === 'number' ? data.risk_score : (overviewDevice?.risk_score ?? 0);

    const mergedDga = useMemo(() => {
        const healthDga = data?.dga_data && Object.keys(data.dga_data).length > 0 ? data.dga_data : {};
        const sampleGases = dgaSample?.gases ?? {};
        const out: Record<string, any> = { ...healthDga };
        GAS_ORDER.forEach((k) => {
            const sample = sampleGases[k];
            const current = out[k];
            const hasCurrent = Array.isArray(current?.values) && current.values.length > 0;
            if (sample?.values?.length && !hasCurrent) out[k] = sample;
        });
        return out;
    }, [data, dgaSample]);

    const dgaRows = GAS_ORDER
        .filter((k) => Array.isArray(mergedDga[k]?.values) && mergedDga[k].values.length > 0)
        .map((k) => ({
            label: GAS_LABELS[k],
            latest: Number(mergedDga[k].values.slice(-1)[0]).toFixed(2),
            count: mergedDga[k].values.length,
            ts: mergedDga[k].timestamps?.slice(-1)[0] || mergedDga[k].timestamps?.[0] || '样本序列',
        }));

    const rulLow = rul != null ? Math.max(1, +(rul - 2.2).toFixed(1)) : undefined;
    const rulHigh = rul != null ? +(rul + 3.0).toFixed(1) : undefined;

    const displayHealth = {
        ...(data || {}),
        health_index: healthIndex,
        predicted_rul: rul,
        risk_score: riskScore,
        primary_threat: data?.primary_threat || overviewDevice?.primary_threat || '暂无突出威胁',
        dga_data: mergedDga,
    };

    if (loading || !overviewDevice) return <div className="flex items-center justify-center flex-1 text-[#209F84] animate-pulse">正在载入 AI 分析引擎...</div>;

    // 缺陷判定以后端 is_fault 为准（后端正常类中文为"设备正常"，不能用字符串"正常"比较）
    const isFault = !!defectData?.final_fusion_result?.is_fault;
    const isSample = defectData?.data_mode?.mode !== 'realtime';
    const demoNote = defectData?.data_mode?.note as string | undefined;

    const EVIDENCE_CN: Record<string, string> = { bert: '巡检记录', cnn: '油色谱', yolo: '图像检查' };
    const uaText = rul != null
        ? `样本估算区间 ${rulLow} ~ ${rulHigh} 年；基于公开样本与确定性健康模型生成，非现场实时采集。`
        : '样本健康指数已由统一概览口径提供，供趋势研判参考。';

    return (
        <div className="flex flex-col min-h-full">
            {isSample && demoNote && (
                <div className="mb-3 px-4 py-2 rounded-lg bg-[#e8f3fe] border border-[#9cc9f4] text-[#3d8fe8] text-[11px] leading-relaxed flex items-start">
                    <Info className="w-3.5 h-3.5 mr-2 flex-shrink-0 mt-0.5" />
                    <span>{demoNote}</span>
                </div>
            )}
        <div className="flex min-h-full space-x-4">
            {/* Left: Device Insights */}
            <div className="w-80 flex flex-col space-y-4">
                <Card className="glass-panel border-0 bg-transparent h-fit">
                    <CardHeader className="pb-2">
                        <div className="flex items-center text-[#209F84] text-xs font-bold uppercase mb-2">
                            <Info className="w-3 h-3 mr-2" /> 设备摘要
                        </div>
                        <CardTitle className="text-xl text-[#333333]">
                            {ledgerInfo?.name ?? '变压器'}
                            <span className="text-xs text-[#666666] font-normal ml-2">{deviceId?.toUpperCase()}</span>
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3 pt-2">
                        <div className="flex justify-between text-xs">
                            <span className="text-[#666666]">型号</span>
                            <span className="text-[#333333]">{ledgerInfo?.model ?? '—'}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                            <span className="text-[#666666]">额定容量 / 电压</span>
                            <span className="text-[#333333]">{ledgerInfo ? `${ledgerInfo.capacity_mva} MVA · ${ledgerInfo.voltage_kv}kV` : '—'}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                            <span className="text-[#666666]">制造单位</span>
                            <span className="text-[#333333]">{ledgerInfo?.manufacturer ?? '—'}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                            <span className="text-[#666666]">投运日期</span>
                            <span className="text-[#333333]">{ledgerInfo?.commission_date ?? '—'}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                            <span className="text-[#666666]">冷却方式</span>
                            <span className="text-[#333333]">{ledgerInfo?.cooling ?? '—'}</span>
                        </div>
                        {ledgerInfo?.serial_no && (
                            <div className="flex justify-between text-xs">
                                <span className="text-[#666666]">出厂编号</span>
                                <span className="text-[#333333]">{ledgerInfo.serial_no}</span>
                            </div>
                        )}
                        {ledgerInfo?.vector_group && (
                            <div className="flex justify-between text-xs">
                                <span className="text-[#666666]">接线组别</span>
                                <span className="text-[#333333]">{ledgerInfo.vector_group}</span>
                            </div>
                        )}
                        {ledgerInfo?.operation_status && (
                            <div className="flex justify-between text-xs">
                                <span className="text-[#666666]">运行状态</span>
                                <span className="text-[#209F84]">{ledgerInfo.operation_status}</span>
                            </div>
                        )}
                        <div className="flex justify-between text-xs pt-2 border-t border-[#dcdfe6]">
                            <span className="text-[#666666]">当前健康分</span>
                            <span className={`font-bold ${healthIndex < 60 ? 'text-[#ff5b01]' : 'text-[#209F84]'}`}>
                                {healthIndex.toFixed(1)}
                            </span>
                        </div>
                        <div className="flex justify-between text-xs">
                            <span className="text-[#666666]">预测剩余寿命</span>
                            <span className="font-bold text-[#333333]">
                                {rul.toFixed(1)} 年
                            </span>
                        </div>
                        <div className="p-3 bg-[#e6f4f0] rounded-lg border border-[#b3ddd5]">
                            <div className="text-[10px] text-[#209F84] font-bold uppercase mb-1">AI 建议</div>
                            <div className="text-[11px] text-[#333333] leading-relaxed mb-3 italic">
                                {data?.diagnosis_summary || '暂无补充建议，请结合标准评价结论与现场试验结果综合研判。'}
                            </div>
                            <div className="text-[9px] text-[#666666] mb-2">
                                <span className="text-[#209F84] font-bold mr-1">置信度量化:</span> {uaText}
                            </div>

                            <div className="pt-3 border-t border-[#dcdfe6]">
                                <div className="text-[10px] text-[#209F84] font-bold uppercase mb-2">综合缺陷研判</div>
                                <div className="flex items-center justify-between mb-3">
                                    <div className="text-sm font-bold text-[#333333]">
                                        判定结果: <span className={`inline-block whitespace-nowrap ${isFault ? "text-[#ff5b01]" : "text-[#5ba83c]"}`}>
                                            {defectData?.final_fusion_result?.final_result_cn || "分析中..."}
                                        </span>
                                    </div>
                                    <div className="text-[10px] text-[#666666]">
                                        置信度: {((defectData?.final_fusion_result?.final_confidence ?? 0) * 100).toFixed(1)}%
                                    </div>
                                </div>
                                <div className="space-y-1.5 mb-3">
                                    {defectData?.source_evidence && Object.entries(defectData.source_evidence).filter(([k]) => k !== 'image_url' && k !== 'ai_reasoning').map(([source, text]) => (
                                        <div key={source} className="flex items-start text-[9px] text-[#666666] leading-tight">
                                            <span className="text-[#209F84] font-bold mr-1">{EVIDENCE_CN[source] ?? source}:</span>
                                            {text as string}
                                        </div>
                                    ))}
                                </div>
                                <div className="w-full bg-[#f8f8fa] h-1 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-[#209F84]"
                                        style={{ width: `${(defectData?.final_fusion_result?.final_confidence * 100) || 0}%` }}
                                    />
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <div className="flex-1 glass-panel rounded-xl p-5 flex flex-col overflow-hidden">
                    <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center text-[#209F84]">
                            <History className="w-4 h-4 mr-2" />
                            <span className="text-sm font-bold uppercase tracking-wider">检修 / 运维历史</span>
                        </div>
                        <span className="text-[10px] text-[#666666]">标准样本记录</span>
                    </div>
                    <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2">
                        {history.length === 0 && (
                            <p className="text-xs text-[#666666] py-3">暂无历史检修记录。</p>
                        )}
                        {history.map((h, i) => (
                            <div key={i} className="rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] p-3">
                                <div className="flex items-center justify-between text-[11px]">
                                    <span className="text-[#209F84] font-medium">{h.type}</span>
                                    <span className="text-[#666666] tabular-nums">{h.date}</span>
                                </div>
                                <p className="text-[11px] text-[#333333] leading-relaxed mt-1.5">{h.result}</p>
                                <p className="text-[10px] text-[#666666] mt-1">记录人：{h.operator}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Middle: Multi-modal evidence + DGA table */}
            <div className="flex-1 flex flex-col space-y-4">
                <ModalityFusion health={displayHealth} defect={defectData} deviceId={deviceId} isSample={isSample} />
                {/* DGA 组分分析（样本序列） */}
                <div className="glass-panel rounded-xl p-5 flex flex-col">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center text-[#209F84]">
                            <Table className="w-4 h-4 mr-2" />
                            <span className="text-sm font-bold uppercase tracking-wider">DGA 组分样本序列</span>
                        </div>
                        <span className="text-[10px] text-[#666666]">油色谱标准样本序列</span>
                    </div>
                    <div className="flex-1 overflow-y-auto custom-scrollbar">
                        <table className="w-full text-left">
                            <thead className="text-[11px] text-[#666666] uppercase border-b border-[#dcdfe6]">
                                <tr>
                                    <th className="pb-2 font-medium">监测项目</th>
                                    <th className="pb-2 font-medium">样本最新值</th>
                                    <th className="pb-2 font-medium">样本趋势</th>
                                </tr>
                            </thead>
                            <tbody className="text-xs">
                                {dgaRows.map((item) => (
                                    <tr key={item.label} className="border-b border-[#dcdfe6] last:border-0 hover:bg-[#f8f8fa] transition-colors">
                                        <td className="py-3 text-[#333333] font-medium">{item.label}</td>
                                        <td className="py-3">
                                            <span className="text-[#333333] font-mono">{item.latest}</span>
                                            <span className="ml-1 text-[10px] text-[#666666]">µL/L</span>
                                        </td>
                                        <td className="py-3 text-[#666666] text-[11px]">
                                            {item.count} 个采样点 · 最新时刻 {item.ts}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            {/* Right: Reasoning & Chat */}
            <div className="w-[450px] flex flex-col space-y-4">
                {/* 健康度演化 + 剩余寿命不确定度 */}
                <div className="glass-panel rounded-xl p-5">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center text-[#209F84]">
                            <BarChart3 className="w-4 h-4 mr-2" />
                            <span className="text-sm font-bold uppercase tracking-wider">健康度演化曲线</span>
                        </div>
                        <span className="text-[10px] text-[#666666]">剩余寿命趋势测算</span>
                    </div>
                    <div className="h-[220px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={hiData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#ebeef5" vertical={false} />
                                <XAxis dataKey="name" stroke="#666666" fontSize={10} tickLine={false} axisLine={false} />
                                <YAxis stroke="#666666" fontSize={10} tickLine={false} axisLine={false} domain={[0, 100]} />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#ffffff', border: '1px solid #dcdfe6', borderRadius: '8px', color: '#333333' }}
                                    itemStyle={{ color: '#209F84' }}
                                />
                                <Line type="monotone" dataKey="HI" stroke="#209F84" strokeWidth={2} dot={{ fill: '#209F84', r: 3 }} activeDot={{ r: 5, strokeWidth: 0 }} />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                    <div className="mt-3 pt-3 border-t border-[#dcdfe6] grid grid-cols-3 gap-2 text-center">
                        <div>
                            <div className="text-[9px] text-[#666666] uppercase">剩余寿命趋势</div>
                            <div className="text-sm font-bold text-[#333333]">{rul.toFixed(1)}</div>
                            <div className="text-[9px] text-[#666666]">年 · 样本测算</div>
                        </div>
                        <div>
                            <div className="text-[9px] text-[#666666] uppercase">样本估算区间</div>
                            <div className="text-sm font-bold text-[#333333]">{rulLow}~{rulHigh}</div>
                            <div className="text-[9px] text-[#666666]">年 · 确定性口径</div>
                        </div>
                        <div>
                            <div className="text-[9px] text-[#666666] uppercase">综合风险评分</div>
                            <div className="text-sm font-bold text-[#333333]">{riskScore.toFixed(1)}</div>
                            <div className="text-[9px] text-[#666666]">分 · 油色谱联动</div>
                        </div>
                    </div>
                </div>
                {/* AI 助手 */}
                <div className="min-h-[500px] flex-1 glass-panel rounded-xl overflow-hidden">
                    <AIChat onNavigate={onNavigateAgent} />
                </div>
            </div>
        </div>
        {/* 报告闭环（五段流程 + 一键生成报告视图） */}
        <div className="mt-4">
            <ReportWorkorder deviceId={deviceId} health={displayHealth} defect={defectData} />
        </div>
        </div>
    );
}
