import React, { useState } from 'react';
import { Database, Zap, ChevronDown, ChevronRight } from 'lucide-react';
import { useData } from '../lib/store';

const statusDot = (status: string) => {
    if (status === '严重' || status === '异常') return 'bg-red-500 led-pulse-red';
    if (status === '关注') return 'bg-[#fcaa00] led-pulse-yellow';
    return 'bg-[#6fba47] led-pulse-green';
};

/** 资源导航：从统一数据层读取变电站—变压器层级与实时汇总状态。 */
export default function DeviceTree({
    selectedId,
}: {
    selectedId?: string;
}) {
    const { overview, navigate, overviewLoading } = useData();
    const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

    return (
        <div className="flex flex-col h-full text-sm text-[#333333]">
            <div className="px-4 py-3 border-b border-[#dcdfe6] font-medium text-[#209F84] flex items-center">
                <Database className="w-4 h-4 mr-2" />
                设备导航
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
                {overviewLoading && (
                    <p className="text-xs text-[#666666] p-3 animate-pulse">正在加载设备清单…</p>
                )}
                {!overviewLoading && !overview && (
                    <p className="text-xs text-[#666666] p-3">暂未获取到设备清单，请稍后刷新。</p>
                )}
                {overview?.stations.map((station) => (
                    <div key={station.id} className="space-y-1">
                        <button
                            onClick={() => setCollapsed((c) => ({ ...c, [station.id]: !c[station.id] }))}
                            className="w-full flex items-center px-2 py-1.5 text-[#333333] hover:text-[#333333] hover:bg-[#f8f8fa] rounded-md"
                        >
                            {collapsed[station.id]
                                ? <ChevronRight className="w-4 h-4 mr-1 text-[#666666]" />
                                : <ChevronDown className="w-4 h-4 mr-1 text-[#209F84]" />}
                            <span className="truncate">{station.name}</span>
                            <span className="ml-auto text-[10px] text-[#666666]">{station.devices.length} 台</span>
                        </button>
                        {!collapsed[station.id] && (
                            <div className="ml-4 border-l border-[#dcdfe6] space-y-1">
                                {station.devices.map((tr) => (
                                    <button
                                        key={tr.equipment_id}
                                        onClick={() => navigate('reasoning', { deviceId: tr.equipment_id })}
                                        className={`w-full flex items-center justify-between px-3 py-2 rounded-md transition-all ${selectedId === tr.equipment_id
                                            ? 'bg-[#e6f4f0] text-[#209F84] border border-[#b3ddd5]'
                                            : 'hover:bg-[#f8f8fa] border border-transparent'
                                            }`}
                                    >
                                        <div className="flex items-center space-x-2 truncate">
                                            <Zap className="w-3 h-3 text-[#209F84]" />
                                            <span className="truncate">{tr.name}</span>
                                        </div>
                                        <span className={`w-1.5 h-1.5 rounded-full ${statusDot(tr.status)}`} />
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
