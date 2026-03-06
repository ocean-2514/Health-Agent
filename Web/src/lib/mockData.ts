export const mockHierarchy = {
    station: "110kV 黎明变电站",
    transformers: [
        { id: "tr-01", name: "1号主变压器", status: "green", score: 92 },
        { id: "tr-02", name: "2号主变压器", status: "yellow", score: 76 },
        { id: "tr-03", name: "3号主变压器", status: "red", score: 45 },
    ]
};

export const mockWarnings = [
    { id: 1, level: "red", time: "10:24:12", device: "3号主变压器", desc: "H2浓度急剧上升突破阈值" },
    { id: 2, level: "yellow", time: "09:12:05", device: "2号主变压器", desc: "局部放电活动频繁" },
    { id: 3, level: "yellow", time: "昨天 15:30", device: "1号主变压器", desc: "环境温度偏高" },
];

export const mockRadarData = [
    { subject: '绝缘性能', A: 90, fullMark: 100 },
    { subject: '运行负载', A: 85, fullMark: 100 },
    { subject: '动作次数', A: 70, fullMark: 100 },
    { subject: '油中气体', A: 60, fullMark: 100 },
    { subject: '环境温升', A: 95, fullMark: 100 },
    { subject: '剩余寿命', A: 80, fullMark: 100 },
];

export const mockDGAData = [
    { gas: 'H2', value: '120.5', unit: 'µL/L', status: 'normal' },
    { gas: 'CH4', value: '45.2', unit: 'µL/L', status: 'normal' },
    { gas: 'C2H2', value: '5.1', unit: 'µL/L', status: 'warning' },
    { gas: 'C2H4', value: '88.9', unit: 'µL/L', status: 'normal' },
    { gas: 'C2H6', value: '30.4', unit: 'µL/L', status: 'normal' },
    { gas: 'CO', value: '450.0', unit: 'µL/L', status: 'normal' },
    { gas: 'CO2', value: '4200.0', unit: 'µL/L', status: 'normal' },
];

export const mockChatHistory = [
    { role: 'ai', content: '您好，管控助手已就绪。当前3号主变压器DGA特征表现为高温过热兼高能放电，请问需要执行什么深度分析？' }
];

export const mockApprovalTasks = [
    { id: "T-20231024-01", device: "3号主变压器", type: "停电检修建议", date: "2023-10-24 10:30", status: "pending" },
    { id: "T-20231024-02", device: "2号主变压器", type: "增加油样检测频次", date: "2023-10-24 09:15", status: "pending" },
    { id: "T-20231023-05", device: "1号主变压器", type: "冷却系统排查", date: "2023-10-23 16:00", status: "approved" },
];
