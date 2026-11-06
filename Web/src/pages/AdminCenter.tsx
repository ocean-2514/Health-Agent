import React, { useEffect, useState } from 'react';
import {
    Cpu, Server, Gauge, Cpu as ChipIcon, RefreshCw, ExternalLink,
    ShieldCheck, Users, Activity, HardDrive, CheckCircle2, XCircle,
} from 'lucide-react';
import {
    edgeHealth, edgeSystemStats, edgeGpuStatus, edgeHalProbe,
    edgeModelStats, edgeLlmStatus,
} from '../lib/api';

function Card({ title, icon, children }: {
    title: string; icon: React.ReactNode; children: React.ReactNode;
}) {
    return (
        <div className="rounded-xl border border-[#dcdfe6] bg-[#f8f8fa] p-4">
            <div className="flex items-center space-x-2 mb-3 text-[#209F84]">
                {icon}<h3 className="text-sm font-semibold text-[#333333]">{title}</h3>
            </div>
            {children}
        </div>
    );
}

function Stat({ label, value, unit, tone = 'text-[#333333]' }: {
    label: string; value: React.ReactNode; unit?: string; tone?: string;
}) {
    return (
        <div className="rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] p-3">
            <div className={`text-xl font-bold ${tone}`}>
                {value}{unit && <span className="text-xs text-[#666666] ml-0.5">{unit}</span>}
            </div>
            <div className="text-xs text-[#666666] mt-1">{label}</div>
        </div>
    );
}

function StatusDot({ ok, okText, badText }: { ok: boolean; okText: string; badText: string }) {
    return (
        <div className="flex items-center space-x-2 text-sm">
            {ok ? (
                <CheckCircle2 className="w-4 h-4 text-[#5ba83c]" />
            ) : (
                <XCircle className="w-4 h-4 text-[#ff5b01]" />
            )}
            <span className={ok ? 'text-[#5ba83c]' : 'text-[#ff5b01]'}>{ok ? okText : badText}</span>
        </div>
    );
}

const EDGE_MODELS = [
    { name: '电力缺陷检测 YOLO', kind: '视觉' },
    { name: '安全帽检测 YOLO', kind: '视觉' },
    { name: '油色谱 1D-CNN', kind: '时序' },
    { name: '日志分类 TextCNN', kind: '文本' },
    { name: 'COCO 零样本 YOLO', kind: '视觉' },
];

export default function AdminCenter() {
    const [health, setHealth] = useState<any>(null);
    const [sys, setSys] = useState<Record<string, any> | null>(null);
    const [gpu, setGpu] = useState<Record<string, any> | null>(null);
    const [hal, setHal] = useState<Record<string, any> | null>(null);
    const [modelStats, setModelStats] = useState<Record<string, any> | null>(null);
    const [llm, setLlm] = useState<Record<string, any> | null>(null);
    const [loading, setLoading] = useState(false);

    const loadAll = async () => {
        setLoading(true);
        const [h, s, g, hp, m, l] = await Promise.all([
            edgeHealth(), edgeSystemStats(), edgeGpuStatus(),
            edgeHalProbe(), edgeModelStats(), edgeLlmStatus(),
        ]);
        setHealth(h); setSys(s); setGpu(g); setHal(hp); setModelStats(m); setLlm(l);
        setLoading(false);
    };

    useEffect(() => { loadAll(); }, []);

    const edgeOnline = !!health;
    const backends = hal?.backends ?? {};

    return (
        <div className="space-y-4">
            {/* 页头 */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-lg font-bold text-[#333333]">系统管理</h2>
                    <p className="text-xs text-[#666666] mt-0.5">
                        后端运维：服务网关、系统资源、模型与国产异构适配，数据经同源网关实时读取
                    </p>
                </div>
                <div className="flex items-center space-x-2">
                    <button
                        onClick={loadAll}
                        className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] text-xs text-[#333333] hover:bg-[#f2f4f6]"
                    >
                        <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                        <span>刷新</span>
                    </button>
                    <a
                        href="http://127.0.0.1:8080/"
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-[#e6f4f0] border border-[#9cd2c7] text-xs text-[#209F84] hover:bg-[#dceee9]"
                    >
                        <ExternalLink className="w-3.5 h-3.5" />
                        <span>打开边缘平台完整界面（独立端口 8080）</span>
                    </a>
                </div>
            </div>

            {/* 网关状态 */}
            <Card title="服务网关状态" icon={<Server className="w-4 h-4" />}>
                <div className="grid grid-cols-3 gap-4">
                    <StatusDot ok={edgeOnline} okText="边缘推理服务在线（8080）" badText="边缘推理服务未连接" />
                    <StatusDot ok={!!llm} okText="边缘服务接口可达" badText="边缘接口不可达" />
                    <div className="flex items-center space-x-2 text-sm text-[#666666]">
                        <ShieldCheck className="w-4 h-4 text-[#209F84]" />
                        <span>浏览器仅与大脑同源通信，后端服务端口不对外暴露</span>
                    </div>
                </div>
            </Card>

            {/* 系统资源 */}
            <Card title="实时系统资源" icon={<Cpu className="w-4 h-4" />}>
                <div className="grid grid-cols-4 gap-3">
                    <Stat label="CPU 占用" value={sys?.cpu ?? '—'} unit="%" tone="text-[#3d8fe8]" />
                    <Stat label="内存占用" value={sys?.memory ?? '—'} unit="%" tone="text-[#d99000]" />
                    <Stat label="GPU 显存占用" value={sys?.gpu_mem ?? gpu?.memory_used ?? '—'} unit="GB" tone="text-[#209F84]" />
                    <Stat label="今日推理次数" value={sys?.inference_today ?? '—'} tone="text-[#5ba83c]" />
                    <Stat label="已加载模型数" value={sys?.models_loaded ?? '—'} tone="text-[#209F84]" />
                    <Stat label="平均推理延迟" value={sys?.avg_latency ?? '—'} unit="ms" tone="text-[#8a63e0]" />
                    <Stat label="在线摄像头" value={sys?.cameras_online ?? '—'} unit={`/ ${sys?.cameras_total ?? 0}`} tone="text-[#3d8fe8]" />
                    <Stat
                        label="GPU 设备"
                        value={gpu?.available ? (gpu.name ?? 'GPU') : 'CPU 模式'}
                        tone={gpu?.available ? 'text-[#5ba83c]' : 'text-[#666666]'}
                    />
                </div>
            </Card>

            {/* 模型清单与统计 */}
            <div className="grid grid-cols-2 gap-4">
                <Card title="边缘样机模型清单（启动同时加载）" icon={<ChipIcon className="w-4 h-4" />}>
                    <div className="space-y-2">
                        {EDGE_MODELS.map((m, i) => (
                            <div key={i} className="flex items-center justify-between rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] px-3 py-2">
                                <span className="text-sm text-[#333333]">{m.name}</span>
                                <span className="text-xs px-2 py-0.5 rounded bg-[#e6f4f0] text-[#209F84] border border-[#b3ddd5]">
                                    {m.kind}
                                </span>
                            </div>
                        ))}
                        <div className="flex items-center justify-between rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] px-3 py-2">
                            <span className="text-sm text-[#333333]">Qwen2.5-VL 视觉大模型（按需加载）</span>
                            <span className={`text-xs px-2 py-0.5 rounded border ${llm?.loaded
                                ? 'bg-[#eef7e8] text-[#5ba83c] border-[#c4e3b0]'
                                : 'bg-[#f8f8fa] text-[#666666] border-[#dcdfe6]'}`}>
                                {llm?.loaded ? '已加载' : '按需'}
                            </span>
                        </div>
                    </div>
                </Card>

                <Card title="模型运行统计" icon={<Activity className="w-4 h-4" />}>
                    <div className="grid grid-cols-2 gap-3">
                        <Stat label="累计告警" value={modelStats?.total_alerts ?? '—'} tone="text-[#d99000]" />
                        <Stat label="误报数" value={modelStats?.false_positives ?? '—'} tone="text-[#ff5b01]" />
                        <Stat label="复核次数" value={modelStats?.review_count ?? '—'} tone="text-[#3d8fe8]" />
                        <Stat label="当前准确率" value={modelStats?.accuracy ?? '—'} tone="text-[#5ba83c]" />
                    </div>
                </Card>
            </div>

            {/* 国产异构适配 */}
            <Card title="国产异构算力适配（HAL）" icon={<HardDrive className="w-4 h-4" />}>
                <div className="grid grid-cols-2 gap-3">
                    {Object.entries(backends).map(([key, b]: [string, any]) => (
                        <div key={key} className="rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] p-3">
                            <div className="flex items-center justify-between mb-1.5">
                                <span className="text-sm text-[#333333]">{b.display_name ?? key}</span>
                                <span className={`text-xs px-2 py-0.5 rounded border ${b.native_available
                                    ? 'bg-[#eef7e8] text-[#5ba83c] border-[#c4e3b0]'
                                    : 'bg-[#fbeed2] text-[#d99000] border-[#f0d9a8]'}`}>
                                    {b.native_available ? '原生可用' : 'CPU 回退'}
                                </span>
                            </div>
                            <p className="text-xs text-[#666666] leading-relaxed">
                                {b.native_available
                                    ? `执行提供者：${b.ep ?? 'native'}`
                                    : (b.reason || '未检测到原生 SDK，当前回退 ONNX Runtime CPU，不伪装加速')}
                            </p>
                        </div>
                    ))}
                    <div className="col-span-2 rounded-lg bg-[#f8f8fa] border border-[#dcdfe6] p-3">
                        <p className="text-xs text-[#666666] leading-relaxed">
                            HAL 将厂商公开规格（spec）与本机实际运行态（runtime）分离：无真机 SDK 时回退 CPU 并明确标注
                            cpu-fallback，绝不把软件回退伪装成国产硬件加速。当前架构 {hal?.arch ?? '—'}。
                        </p>
                    </div>
                </div>
            </Card>

            {/* 账号说明 */}
            <Card title="账号与权限" icon={<Users className="w-4 h-4" />}>
                <p className="text-xs text-[#666666] leading-relaxed">
                    账号管理在边缘平台完整界面中进行，新增/删除用户需管理员身份并通过登录鉴权，接口对密码做脱敏处理。
                    本页为运维概览，不直接展示账号明细以避免敏感信息暴露；正式部署时应替换演示 CA 与默认口令。
                </p>
            </Card>
        </div>
    );
}
