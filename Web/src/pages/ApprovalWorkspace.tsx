import React, { useState } from 'react';
import { ClipboardList, CheckSquare, XSquare, Download, Printer, FileText, UserCheck, Send } from 'lucide-react';

export default function ApprovalWorkspace() {
    const [selectedTask, setSelectedTask] = useState<any>(null);
    const [remark, setRemark] = useState('');

    const tasks = [
        { id: 't1', device: '1号主变', type: 'DGA趋势异常', time: '2小时前', severity: 'medium', aiAdvice: '建议加强绝缘监测，三个月后再次复检。' },
        { id: 't2', device: '4号主变', type: '重瓦斯告警', time: '5分钟前', severity: 'critical', aiAdvice: '立即停运检修，检查内部是否存在短路放电。' },
    ];

    const currentTask = selectedTask || tasks[0];

    return (
        <div className="flex min-h-full space-x-4">
            {/* Left: Task Queue */}
            <div className="w-72 glass-panel rounded-xl flex flex-col overflow-hidden">
                <div className="px-4 py-3 border-b border-white/10 font-medium text-cyan-400 flex items-center">
                    <ClipboardList className="w-4 h-4 mr-2" />
                    待复核队列
                </div>
                <div className="flex-1 overflow-y-auto p-2 space-y-2">
                    {tasks.map(task => (
                        <button
                            key={task.id}
                            onClick={() => setSelectedTask(task)}
                            className={`w-full text-left p-3 rounded-lg border transition-all ${currentTask.id === task.id
                                ? 'bg-cyan-500/10 border-cyan-500/30'
                                : 'glass-panel border-transparent hover:border-white/10'
                                }`}
                        >
                            <div className="flex justify-between items-start mb-2">
                                <span className="text-xs font-bold text-white">{task.device}</span>
                                <span className={`text-[10px] px-1.5 py-0.5 rounded ${task.severity === 'critical' ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-400'
                                    }`}>
                                    {task.severity === 'critical' ? '紧急' : '重要'}
                                </span>
                            </div>
                            <div className="text-[11px] text-gray-300 truncate mb-1">{task.type}</div>
                            <div className="text-[10px] text-gray-500">{task.time}</div>
                        </button>
                    ))}
                </div>
            </div>

            {/* Middle: Review Area */}
            <div className="flex-1 flex flex-col space-y-4">
                <div className="flex-1 flex space-x-4 min-h-[600px]">
                    {/* AI Info (Readonly) */}
                    <div className="flex-1 glass-panel rounded-xl p-6 flex flex-col">
                        <div className="flex items-center text-cyan-400 text-sm font-bold uppercase mb-6">
                            <FileText className="w-4 h-4 mr-2" /> AI 生成建议详情
                        </div>
                        <div className="flex-1 space-y-6">
                            <section>
                                <label className="text-[10px] text-gray-500 uppercase tracking-widest block mb-2">诊断结论</label>
                                <div className="text-lg text-white font-semibold">{currentTask.type}</div>
                            </section>
                            <section>
                                <label className="text-[10px] text-gray-500 uppercase tracking-widest block mb-1.5">维护建议</label>
                                <div className="p-4 bg-white/5 rounded-xl border border-white/5 text-sm text-gray-300 leading-relaxed italic">
                                    “{currentTask.aiAdvice}”
                                </div>
                            </section>
                            <section>
                                <label className="text-[10px] text-gray-500 uppercase tracking-widest block mb-2">数据依据</label>
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="p-3 rounded-lg bg-black/40 border border-white/5">
                                        <div className="text-[10px] text-gray-500 mb-1">健康指数</div>
                                        <div className="text-xl font-bold text-amber-500">74.2</div>
                                    </div>
                                    <div className="p-3 rounded-lg bg-black/40 border border-white/5">
                                        <div className="text-[10px] text-gray-500 mb-1">故障概率</div>
                                        <div className="text-xl font-bold text-red-500">82%</div>
                                    </div>
                                </div>
                            </section>
                        </div>
                    </div>

                    {/* Expert Action (Editable) */}
                    <div className="flex-1 glass-panel rounded-xl p-6 flex flex-col border-cyan-500/20 bg-cyan-500/[0.02]">
                        <div className="flex items-center text-cyan-400 text-sm font-bold uppercase mb-6">
                            <UserCheck className="w-4 h-4 mr-2" /> 专家审核录入
                        </div>
                        <div className="flex-1 space-y-6">
                            <section>
                                <label className="text-[10px] text-gray-500 uppercase tracking-widest block mb-2">审核状态</label>
                                <div className="flex space-x-3">
                                    <button className="flex-1 flex items-center justify-center space-x-2 px-4 py-2 bg-green-500/10 border border-green-500/40 text-green-400 rounded-lg text-xs font-semibold hover:bg-green-500/20 transition-all">
                                        <CheckSquare className="w-4 h-4" /> <span>核准签发</span>
                                    </button>
                                    <button className="flex-1 flex items-center justify-center space-x-2 px-4 py-2 bg-red-500/10 border border-red-500/40 text-red-400 rounded-lg text-xs font-semibold hover:bg-red-500/20 transition-all">
                                        <XSquare className="w-4 h-4" /> <span>驳回修改</span>
                                    </button>
                                </div>
                            </section>
                            <section className="flex-1 flex flex-col">
                                <label className="text-[10px] text-gray-500 uppercase tracking-widest block mb-2">审核意见及备注</label>
                                <textarea
                                    value={remark}
                                    onChange={(e) => setRemark(e.target.value)}
                                    placeholder="请输入专家审核意见..."
                                    className="flex-1 w-full bg-black/30 border border-white/10 rounded-xl p-4 text-sm text-gray-200 focus:outline-none focus:border-cyan-500/50 resize-none"
                                />
                            </section>
                        </div>
                    </div>
                </div>

                {/* Bottom ActionBar */}
                <div className="h-12 glass-panel rounded-xl flex items-center justify-between px-6">
                    <div className="flex space-x-4">
                        <button className="p-2 text-gray-400 hover:text-cyan-400 transition-colors" title="PDF下载">
                            <Download className="w-5 h-5" />
                        </button>
                        <button className="p-2 text-gray-400 hover:text-cyan-400 transition-colors" title="打印报告">
                            <Printer className="w-5 h-5" />
                        </button>
                    </div>
                    <button className="px-8 py-1.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white rounded-full text-xs font-bold uppercase tracking-wider flex items-center shadow-[0_4px_15px_rgba(0,208,255,0.3)] transition-all active:scale-95">
                        确认签发指令 <Send className="w-3 h-3 ml-2" />
                    </button>
                </div>
            </div>
        </div>
    );
}
