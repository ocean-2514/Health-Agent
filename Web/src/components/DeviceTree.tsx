import React from 'react';
import { Database, Zap, ChevronRight, ChevronDown } from 'lucide-react';

export default function DeviceTree({ onSelectTransformer, onSelectSubstation, selectedId, selectedSubstationId }: {
    onSelectTransformer: (id: string) => void,
    onSelectSubstation?: (id: string) => void,
    selectedId?: string,
    selectedSubstationId?: string
}) {
    const substations = [
        {
            id: 'station1',
            name: '110kV 黎明变电站',
            transformers: [
                { id: 'tr01', name: '1号主变压器', status: 'normal' },
                { id: 'tr02', name: '2号主变压器', status: 'warning' },
            ]
        },
        {
            id: 'station2',
            name: '220kV 永和变电站',
            transformers: [
                { id: 'tr03', name: '3号主变压器', status: 'normal' }
            ]
        }
    ];

    return (
        <div className="flex flex-col h-full text-sm text-gray-300">
            <div className="px-4 py-3 border-b border-white/10 font-medium text-cyan-400 flex items-center">
                <Database className="w-4 h-4 mr-2" />
                资源导航
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
                {substations.map(station => (
                    <div key={station.id} className="space-y-1">
                        <div
                            onClick={() => onSelectSubstation && onSelectSubstation(station.id)}
                            className={`flex items-center px-2 py-1.5 transition-colors cursor-pointer group rounded-md ${selectedSubstationId === station.id ? 'text-white bg-white/5' : 'text-gray-400 hover:text-white'
                                }`}
                        >
                            <ChevronDown className={`w-4 h-4 mr-1 transition-colors ${selectedSubstationId === station.id ? 'text-cyan-500' : 'text-gray-600 group-hover:text-cyan-500'}`} />
                            <span className="truncate">{station.name}</span>
                        </div>
                        <div className="ml-4 border-l border-white/5 space-y-1">
                            {station.transformers.map(tr => (
                                <button
                                    key={tr.id}
                                    onClick={() => onSelectTransformer(tr.id)}
                                    className={`w-full flex items-center justify-between px-3 py-2 rounded-md transition-all ${selectedId === tr.id
                                        ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20'
                                        : 'hover:bg-white/5 border border-transparent'
                                        }`}
                                >
                                    <div className="flex items-center space-x-2 truncate">
                                        <Zap className={`w-3 h-3 ${tr.status === 'warning' ? 'text-amber-500' : 'text-green-500'}`} />
                                        <span className="truncate">{tr.name}</span>
                                    </div>
                                    <div className={`w-1.5 h-1.5 rounded-full ${tr.status === 'warning' ? 'bg-amber-500 led-pulse-yellow' : 'bg-green-500 led-pulse-green'
                                        }`} />
                                </button>
                            ))}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
