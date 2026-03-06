import React from 'react';
import HealthRadar from '../components/RadarChart';
import DeviceTree from '../components/DeviceTree';
import WarningFlow from '../components/WarningFlow';
import { Card, CardContent, CardHeader, CardTitle } from '../components/Card';
import { CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';

export default function FleetDashboard({
    onNavigateToAI,
    selectedSubstationId,
    onSelectSubstation
}: {
    onNavigateToAI: (id: string) => void,
    selectedSubstationId: string,
    onSelectSubstation: (id: string) => void
}) {
    const substationsData = {
        'station1': {
            name: '110kV 黎明变电站', devices: [
                { id: 'tr01', name: '1号主变压器', score: 92, status: 'normal' },
                { id: 'tr02', name: '2号主变压器', score: 74, status: 'warning' },
            ]
        },
        'station2': {
            name: '220kV 永和变电站', devices: [
                { id: 'tr03', name: '3号主变压器', score: 88, status: 'normal' },
            ]
        }
    };

    const currentStation = substationsData[selectedSubstationId as keyof typeof substationsData] || substationsData['station1'];
    const gridDevices = currentStation.devices;

    return (
        <div className="flex min-h-full space-x-4">
            {/* Sidebar Resources */}
            <div className="w-64 glass-panel rounded-xl overflow-hidden flex flex-col">
                <DeviceTree
                    onSelectTransformer={onNavigateToAI}
                    onSelectSubstation={onSelectSubstation}
                    selectedSubstationId={selectedSubstationId}
                />
            </div>

            {/* Main Content Area */}
            <div className="flex-1 flex flex-col space-y-4">
                {/* Top: Station Health Summary */}
                <div className="h-[500px] flex space-x-4">
                    <div className="flex-1 glass-panel rounded-xl p-6 relative overflow-hidden">
                        <div className="flex justify-between items-start mb-4">
                            <div>
                                <h2 className="text-xl font-bold text-white mb-1">全站健康状态分布对比</h2>
                                <p className="text-sm text-gray-500">{currentStation.name} · 实时监视</p>
                            </div>
                            <div className="text-right">
                                <div className="text-4xl font-bold text-cyan-400 text-glow">92%</div>
                                <div className="text-xs text-gray-500 mt-1 uppercase tracking-wider">整体健康评分</div>
                            </div>
                        </div>
                        <HealthRadar />
                    </div>
                </div>

                {/* Bottom: Device Grid */}
                <div className="min-h-[300px] flex-1 glass-panel rounded-xl p-6 flex flex-col overflow-hidden">
                    <h2 className="text-lg font-bold text-white mb-4">设备网格</h2>
                    <div className="grid grid-cols-4 gap-4 flex-1 overflow-y-auto pr-2 custom-scrollbar">
                        {gridDevices.map(device => (
                            <button
                                key={device.id}
                                onClick={() => onNavigateToAI(device.id)}
                                className="glass-panel p-4 rounded-xl border border-white/5 hover:border-cyan-500/30 hover:bg-white/5 transition-all text-left group"
                            >
                                <div className="flex justify-between items-start mb-3">
                                    <div className={`p-2 rounded-lg ${device.status === 'normal' ? 'bg-green-500/10' : device.status === 'warning' ? 'bg-amber-500/10' : 'bg-red-500/10'
                                        }`}>
                                        {device.status === 'normal' ? (
                                            <CheckCircle2 className="w-5 h-5 text-green-500" />
                                        ) : device.status === 'warning' ? (
                                            <AlertTriangle className="w-5 h-5 text-amber-500" />
                                        ) : (
                                            <XCircle className="w-5 h-5 text-red-500" />
                                        )}
                                    </div>
                                    <div className="text-2xl font-bold text-gray-300 group-hover:text-cyan-400 transition-colors">
                                        {device.score}
                                    </div>
                                </div>
                                <div className="text-sm font-semibold text-gray-200 truncate">{device.name}</div>
                                <div className="text-[10px] text-gray-500 mt-1">ID: {device.id}</div>
                                <div className="mt-3 flex items-center space-x-2">
                                    <div className={`w-2 h-2 rounded-full ${device.status === 'normal' ? 'bg-green-500 led-pulse-green' : device.status === 'warning' ? 'bg-amber-500 led-pulse-yellow' : 'bg-red-500 led-pulse-red'
                                        }`} />
                                    <span className={`text-[10px] ${device.status === 'normal' ? 'text-green-500/80' : device.status === 'warning' ? 'text-amber-500/80' : 'text-red-500/80'
                                        }`}>
                                        {device.status === 'normal' ? '运行平稳' : device.status === 'warning' ? '需关注' : '告警中'}
                                    </span>
                                </div>
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Right: Warnings */}
            <div className="w-80 glass-panel rounded-xl overflow-hidden flex flex-col">
                <WarningFlow />
            </div>
        </div>
    );
}
