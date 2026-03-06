import React, { useEffect, useState } from 'react';
import { AlertCircle, Clock } from 'lucide-react';

const mockLogs = [
    { id: 1, level: 'critical', time: '17:45:12', device: '1号主变', msg: '分接开关动作频率异常' },
    { id: 2, level: 'warning', time: '17:42:05', device: '2号主变', msg: '绕组温度接近阈值' },
    { id: 3, level: 'normal', time: '17:38:22', device: '1号主变', msg: '绝缘电阻自检完成' },
    { id: 4, level: 'warning', time: '17:30:10', device: '3号主变', msg: '环境湿度较大' },
    { id: 5, level: 'critical', time: '17:15:45', device: '1号主变', msg: '氢气含量轻微波动' },
];

export default function WarningFlow() {
    const [logs, setLogs] = useState(mockLogs);

    useEffect(() => {
        const interval = setInterval(() => {
            setLogs(prev => {
                const newLog = {
                    ...prev[Math.floor(Math.random() * prev.length)],
                    id: Date.now(),
                    time: new Date().toLocaleTimeString([], { hour12: false })
                };
                return [newLog, ...prev.slice(0, 9)];
            });
        }, 5000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="flex flex-col h-full">
            <div className="px-4 py-3 border-b border-white/10 font-medium text-cyan-400 flex items-center">
                <AlertCircle className="w-4 h-4 mr-2" />
                实时警告流
            </div>
            <div className="flex-1 overflow-y-auto custom-scrollbar pt-2 px-2">
                <div className="space-y-2">
                    {logs.map(log => (
                        <div key={log.id} className="glass-panel p-3 rounded-lg border-l-4 transition-all duration-300"
                            style={{
                                borderLeftColor: log.level === 'critical' ? '#FF4D4D' : log.level === 'warning' ? '#FFB800' : '#00FF85',
                                backgroundColor: 'rgba(255,255,255,0.02)'
                            }}>
                            <div className="flex items-center justify-between mb-1">
                                <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${log.level === 'critical' ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-400'
                                    }`}>
                                    {log.level}
                                </span>
                                <div className="flex items-center text-[10px] text-gray-500">
                                    <Clock className="w-3 h-3 mr-1" />
                                    {log.time}
                                </div>
                            </div>
                            <div className="text-xs font-semibold text-gray-200 mb-1">{log.device}</div>
                            <div className="text-[11px] text-gray-400 leading-relaxed">{log.msg}</div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
