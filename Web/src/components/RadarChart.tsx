import React from 'react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts';

const defaultData = [
    { subject: '绝缘性能', A: 95, fullMark: 100 },
    { subject: '运行负载', A: 85, fullMark: 100 },
    { subject: '动作次数', A: 92, fullMark: 100 },
    { subject: '油中气体', A: 78, fullMark: 100 },
    { subject: '环境温升', A: 90, fullMark: 100 },
    { subject: '剩余寿命', A: 88, fullMark: 100 },
];

export default function HealthRadar({ data = defaultData }: { data?: any[] }) {
    return (
        <div className="w-full h-full min-h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
                <RadarChart cx="50%" cy="50%" outerRadius="80%" data={data}>
                    <PolarGrid stroke="rgba(255,255,255,0.1)" />
                    <PolarAngleAxis
                        dataKey="subject"
                        tick={{ fill: '#94a3b8', fontSize: 12 }}
                    />
                    <PolarRadiusAxis
                        angle={30}
                        domain={[0, 100]}
                        tick={false}
                        axisLine={false}
                    />
                    <Radar
                        name="健康状态"
                        dataKey="A"
                        stroke="#00d0ff"
                        fill="#00d0ff"
                        fillOpacity={0.3}
                    />
                </RadarChart>
            </ResponsiveContainer>
        </div>
    );
}
