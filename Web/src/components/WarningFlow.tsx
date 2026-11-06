import React, { useEffect, useState, useCallback, useRef } from 'react';
import { AlertCircle, Clock, RefreshCw, WifiOff } from 'lucide-react';
import { edgeAlarms, type EdgeAlarm } from '../lib/api';

const severityStyle = (level: string) => {
    if (level === 'critical') return { bar: '#FF5B01', badge: 'bg-[#f9d9c6] text-[#ff5b01]' };
    if (level === 'warning') return { bar: '#FCAA00', badge: 'bg-amber-500/20 text-[#d99000]' };
    return { bar: '#6FBA47', badge: 'bg-[#e2f2da] text-[#5ba83c]' };
};

const formatTime = (iso: string) => {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

export default function WarningFlow({ onOpenAlarm }: { onOpenAlarm?: (cameraId: string) => void }) {
    const [alarms, setAlarms] = useState<EdgeAlarm[]>([]);
    const [loading, setLoading] = useState(true);
    const [offline, setOffline] = useState(false);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const load = useCallback(async () => {
        try {
            const data = await edgeAlarms();
            // newest first
            const sorted = [...data].sort((a, b) =>
                new Date(b.create_time).getTime() - new Date(a.create_time).getTime()
            );
            setAlarms(sorted);
            setOffline(false);
        } catch {
            setOffline(true);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
        // Poll the REAL endpoint (refresh, not fabrication) so new detections show.
        timerRef.current = setInterval(load, 10000);
        return () => { if (timerRef.current) clearInterval(timerRef.current); };
    }, [load]);

    return (
        <div className="flex flex-col h-full">
            <div className="px-4 py-3 border-b border-[#dcdfe6] font-medium text-[#209F84] flex items-center justify-between">
                <div className="flex items-center">
                    <AlertCircle className="w-4 h-4 mr-2" />
                    告警流
                </div>
                <button
                    onClick={load}
                    title="刷新真实告警"
                    className="text-[#666666] hover:text-[#209F84] transition-colors"
                >
                    <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                </button>
            </div>
            <div className="flex-1 overflow-y-auto custom-scrollbar pt-2 px-2">
                {offline ? (
                    <div className="m-2 p-4 rounded-lg border border-[#f0ac84] bg-[#fdeee6] text-[#ff5b01] text-xs flex items-start">
                        <WifiOff className="w-4 h-4 mr-2 flex-shrink-0 mt-0.5" />
                        <span>现场检测服务暂未连接，无法获取实时告警；请确认采集服务运行后点击刷新。</span>
                    </div>
                ) : loading ? (
                    <p className="text-xs text-[#666666] p-4 animate-pulse">正在加载真实告警…</p>
                ) : alarms.length === 0 ? (
                    <p className="text-xs text-[#666666] p-4">暂无告警。检测到真实缺陷后将在此显示。</p>
                ) : (
                    <div className="space-y-2">
                        {alarms.map(alarm => {
                            const st = severityStyle(alarm.severity);
                            return (
                                <div key={alarm.id}
                                    onClick={() => onOpenAlarm?.(alarm.camera_id)}
                                    className={`glass-panel p-3 rounded-lg border-l-4 ${onOpenAlarm ? 'cursor-pointer hover:border-[#9cd2c7]' : ''}`}
                                    style={{ borderLeftColor: st.bar, backgroundColor: '#f8f8fa' }}
                                    title="点击查看对应监控画面">
                                    <div className="flex items-center justify-between mb-1">
                                        <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${st.badge}`}>
                                            {alarm.severity}
                                        </span>
                                        <div className="flex items-center text-[10px] text-[#666666]">
                                            <Clock className="w-3 h-3 mr-1" />
                                            {formatTime(alarm.create_time)}
                                        </div>
                                    </div>
                                    <div className="text-xs font-semibold text-[#333333] mb-1">{alarm.camera_name}</div>
                                    <div className="text-[11px] text-[#666666] leading-relaxed mb-1">{alarm.result}</div>
                                    <div className="text-[10px] text-[#666666]">
                                        {alarm.algorithm_name} · 置信度 {(alarm.confidence * 100).toFixed(1)}%
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}
