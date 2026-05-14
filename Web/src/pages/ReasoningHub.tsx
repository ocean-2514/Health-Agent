import React, { useEffect, useState, useRef } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import AIChat from '../components/AIChat';
import { Card, CardContent, CardHeader, CardTitle } from '../components/Card';
import { assessHealth, assessDefect } from '../lib/api';
import { Play, Table, BarChart3, History, Info } from 'lucide-react';

export default function ReasoningHub({ deviceId }: { deviceId?: string }) {
    const [data, setData] = useState<any>(null);
    const [defectData, setDefectData] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const requestRef = useRef<boolean>(false);

    useEffect(() => {
        if (requestRef.current) return;
        requestRef.current = true;
        
        setLoading(true);
        Promise.all([
            assessHealth({ id: deviceId }),
            assessDefect({ id: deviceId })
        ]).then(([healthRes, defectRes]) => {
            setData(healthRes);
            setDefectData(defectRes);
            setLoading(false);
        });
    }, [deviceId]);

    const hiData = data?.health_deduction_curve?.x?.map((x: number, i: number) => ({
        name: x,
        HI: data.health_deduction_curve.y[i]
    })) || [];

    const dgaData = data?.dga_data ? [
        { label: 'H2 (氢气)', value: data.dga_data.H2?.values?.slice(-1)[0] || '0.0', unit: 'uL/L', status: 'normal' },
        { label: 'CH4 (甲烷)', value: data.dga_data.CH4?.values?.slice(-1)[0] || '0.0', unit: 'uL/L', status: 'normal' },
        { label: 'C2H2 (乙炔)', value: data.dga_data.C2H2?.values?.slice(-1)[0] || '0.0', unit: 'uL/L', status: 'normal' },
        { label: 'C2H4 (乙烯)', value: data.dga_data.C2H4?.values?.slice(-1)[0] || '0.0', unit: 'uL/L', status: 'warning' },
        { label: 'CO (一氧化碳)', value: data.dga_data.CO?.values?.slice(-1)[0] || '0.0', unit: 'uL/L', status: 'normal' },
        { label: 'CO2 (二氧化碳)', value: data.dga_data.CO2?.values?.slice(-1)[0] || '0.0', unit: 'uL/L', status: 'normal' },
    ] : [
        { label: 'H2 (氢气)', value: '12.5', unit: 'uL/L', status: 'normal' },
        { label: 'CH4 (甲烷)', value: '8.2', unit: 'uL/L', status: 'normal' },
        { label: 'C2H2 (乙炔)', value: '0.1', unit: 'uL/L', status: 'normal' },
        { label: 'C2H4 (乙烯)', value: '15.4', unit: 'uL/L', status: 'warning' },
        { label: 'CO (一氧化碳)', value: '280', unit: 'uL/L', status: 'normal' },
        { label: 'CO2 (二氧化碳)', value: '1450', unit: 'uL/L', status: 'normal' },
    ];

    if (loading) return <div className="flex items-center justify-center flex-1 text-cyan-400 animate-pulse">正在载入 AI 分析引擎...</div>;

    return (
        <div className="flex min-h-full space-x-4">
            {/* Right: Device Insights (Now Left) */}
            <div className="w-80 flex flex-col space-y-4">
                <Card className="glass-panel border-0 bg-transparent h-fit">
                    <CardHeader className="pb-2">
                        <div className="flex items-center text-cyan-400 text-xs font-bold uppercase mb-2">
                            <Info className="w-3 h-3 mr-2" /> 设备摘要
                        </div>
                        <CardTitle className="text-xl text-white">
                            {deviceId === 'tr01' ? '1号主变压器' :
                                deviceId === 'tr02' ? '2号主变压器' :
                                    deviceId === 'tr03' ? '3号主变压器' : '4号主变压器'}
                            ({deviceId?.toUpperCase()})
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4 pt-2">
                        <div className="flex justify-between text-xs">
                            <span className="text-gray-500">投运日期</span>
                            <span className="text-gray-300">2012-05-20</span>
                        </div>
                        <div className="flex justify-between text-xs">
                            <span className="text-gray-500">当前健康分</span>
                            <span className={`font-bold ${data?.health_index < 60 ? 'text-red-400' : 'text-cyan-400'}`}>
                                {data?.health_index !== undefined ? data.health_index.toFixed(1) : '92.5'}
                            </span>
                        </div>
                        <div className="p-3 bg-cyan-500/10 rounded-lg border border-cyan-500/20">
                            <div className="text-[10px] text-cyan-300 font-bold uppercase mb-1">AI 建议</div>
                            <div className="text-[11px] text-gray-200 leading-relaxed mb-3 italic">
                                {data?.diagnosis_summary || (data?.primary_threat === "无显著威胁" ? "设备目前整体运行良好。油中 C2H4 有缓慢上升趋势，建议列入常规观察名单。" : "检测到潜在异常，建议加强巡检周期。")}
                            </div>
                            <div className="text-[9px] text-gray-500 mb-2">
                                <span className="text-cyan-600 font-bold mr-1">置信度量化:</span> {data?.uncertainty_analysis || "常规物理计算"}
                            </div>

                            <div className="pt-3 border-t border-white/10">
                                <div className="text-[10px] text-cyan-300 font-bold uppercase mb-2">三源融合缺陷识别 (D-S)</div>
                                <div className="flex items-center justify-between mb-3">
                                    <div className="text-sm font-bold text-white">
                                        判定结果: <span className={defectData?.final_fusion_result?.final_result_cn !== '正常' ? "text-red-400" : "text-green-400"}>
                                            {defectData?.final_fusion_result?.final_result_cn || "分析中..."}
                                        </span>
                                    </div>
                                    <div className="text-[10px] text-gray-400">
                                        置信度: {(defectData?.final_fusion_result?.final_confidence * 100).toFixed(1)}%
                                    </div>
                                </div>
                                <div className="space-y-1.5 mb-3">
                                    {defectData?.source_evidence && Object.entries(defectData.source_evidence).filter(([k]) => k !== 'image_url').map(([source, text]) => (
                                        <div key={source} className="flex items-start text-[9px] text-gray-400 leading-tight">
                                            <span className="text-cyan-500 font-bold mr-1 uppercase">{source}:</span>
                                            {text as string}
                                        </div>
                                    ))}
                                </div>
                                <div className="w-full bg-white/5 h-1 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-cyan-500"
                                        style={{ width: `${(defectData?.final_fusion_result?.final_confidence * 100) || 0}%` }}
                                    />
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <div className="flex-1 glass-panel rounded-xl p-5 flex flex-col overflow-hidden">
                    <div className="flex items-center mb-4 text-cyan-400">
                        <History className="w-4 h-4 mr-2" />
                        <span className="text-sm font-bold uppercase tracking-wider">运维历史</span>
                    </div>
                    <div className="flex-1 overflow-y-auto custom-scrollbar space-y-4">
                        {[
                            { date: '2025-11-12', event: '预防性维护', tag: 'Routine' },
                            { date: '2025-06-05', event: '油样取检', tag: 'DGA' },
                            { date: '2024-12-20', event: '散热器清理', tag: 'Repair' },
                        ].map((item, i) => (
                            <div key={i} className="relative pl-4 border-l border-white/10 py-1">
                                <div className="absolute left-[-4.5px] top-2 w-[8px] h-[8px] rounded-full bg-cyan-500/40 border border-cyan-500" />
                                <div className="text-[10px] text-gray-500 font-mono mb-1">{item.date}</div>
                                <div className="text-[11px] text-gray-300 font-semibold">{item.event}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Left: Monitoring & Data (Now Middle) */}
            <div className="flex-1 flex flex-col space-y-4">
                <div className="h-[400px] glass-panel rounded-xl overflow-hidden relative">
                    <div className="absolute inset-0 bg-black/40 flex items-center justify-center overflow-hidden">
                        <img
                            src={defectData?.source_evidence?.image_url || "/assets/defects/normal_sample.png"}
                            alt="Detection Evidence"
                            className="w-full h-full object-cover opacity-80"
                        />
                    </div>
                    <div className="absolute top-4 left-4 flex items-center bg-black/60 px-3 py-1.5 rounded-full border border-white/10 backdrop-blur-md">
                        <div className={`w-2 h-2 rounded-full mr-2 ${defectData?.final_fusion_result?.final_result_cn && defectData?.final_fusion_result?.final_result_cn !== '正常' ? 'bg-red-500 led-pulse-red' : 'bg-green-500 led-pulse-green'}`} />
                        <span className="text-[10px] text-white font-mono uppercase tracking-tighter">
                            {defectData?.source_evidence?.image_url ? 'Multi-Modal Evidence: Visual Detection' : 'Live Feed: Station-01-Cam3'}
                        </span>
                    </div>
                </div>
                {/* DGA 组分分析 */}
                <div className="h-[400px] glass-panel rounded-xl p-5 flex flex-col">
                    <div className="flex items-center mb-4 text-cyan-400">
                        <Table className="w-4 h-4 mr-2" />
                        <span className="text-sm font-bold uppercase tracking-wider">DGA 组分实时分析</span>
                    </div>
                    <div className="flex-1 overflow-y-auto custom-scrollbar">
                        <table className="w-full text-left">
                            <thead className="text-[11px] text-gray-500 uppercase border-b border-white/5">
                                <tr>
                                    <th className="pb-2 font-medium">监测项目</th>
                                    <th className="pb-2 font-medium">当前数值</th>
                                    <th className="pb-2 font-medium">运行趋势</th>
                                </tr>
                            </thead>
                            <tbody className="text-xs">
                                {dgaData.map((item, i) => (
                                    <tr key={i} className="border-b border-white/5 last:border-0 hover:bg-white/5 transition-colors group">
                                        <td className="py-3 text-gray-300 font-medium">{item.label}</td>
                                        <td className="py-3">
                                            <span className="text-gray-200">{item.value}</span>
                                            <span className="ml-1 text-[10px] text-gray-500">{item.unit}</span>
                                        </td>
                                        <td className="py-3">
                                            <div className={`w-12 h-1 rounded-full ${item.status === 'warning' ? 'bg-amber-500/50' : 'bg-green-500/50'}`}>
                                                <div
                                                    className={`h-full rounded-full ${item.status === 'warning' ? 'bg-amber-400' : 'bg-green-400'}`}
                                                    style={{ width: item.status === 'warning' ? '80%' : '40%' }}
                                                />
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            {/* Middle: Reasoning & Chat (Now Right) */}
            <div className="w-[450px] flex flex-col space-y-4">
                {/* 健康度演化 */}
                <div className="h-[300px] glass-panel rounded-xl p-5">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center text-cyan-400">
                            <BarChart3 className="w-4 h-4 mr-2" />
                            <span className="text-sm font-bold uppercase tracking-wider">健康度演化曲线</span>
                        </div>
                        <span className="text-[10px] text-gray-500">生命周期推演</span>
                    </div>
                    <div className="h-[calc(100%-2rem)]">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={hiData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                                <XAxis dataKey="name" stroke="#4a5568" fontSize={10} tickLine={false} axisLine={false} />
                                <YAxis stroke="#4a5568" fontSize={10} tickLine={false} axisLine={false} domain={[0, 100]} />
                                <Tooltip
                                    contentStyle={{ backgroundColor: '#1a202c', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' }}
                                    itemStyle={{ color: '#00d0ff' }}
                                />
                                <Line type="monotone" dataKey="HI" stroke="#00d0ff" strokeWidth={2} dot={{ fill: '#00d0ff', r: 3 }} activeDot={{ r: 5, strokeWidth: 0 }} />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>
                {/* AI 助手 */}
                <div className="min-h-[500px] flex-1 glass-panel rounded-xl overflow-hidden">
                    <AIChat />
                </div>
            </div>
        </div>
    );
}
