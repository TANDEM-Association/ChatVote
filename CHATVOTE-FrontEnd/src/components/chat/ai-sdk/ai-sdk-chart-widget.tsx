'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

type ChartConfig = {
  type: 'chart';
  chartType: 'bar' | 'pie' | 'radar' | 'line';
  title: string;
  data: Array<{ label: string; value: number; color?: string }>;
  xAxisLabel?: string;
  yAxisLabel?: string;
};

const DEFAULT_COLORS = [
  '#3b82f6',
  '#10b981',
  '#8b5cf6',
  '#f59e0b',
  '#ef4444',
  '#06b6d4',
  '#ec4899',
  '#84cc16',
];

function resolveColor(color: string | undefined, index: number): string {
  return color ?? DEFAULT_COLORS[index % DEFAULT_COLORS.length];
}

type RechartsData = { label: string; value: number; color: string };

function toRechartsData(
  data: ChartConfig['data'],
): RechartsData[] {
  return data.map((d, i) => ({
    label: d.label,
    value: d.value,
    color: resolveColor(d.color, i),
  }));
}

function BarChartWidget({
  data,
  xAxisLabel,
  yAxisLabel,
}: {
  data: RechartsData[];
  xAxisLabel?: string;
  yAxisLabel?: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 24 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11, fill: '#94a3b8' }}
          label={
            xAxisLabel
              ? { value: xAxisLabel, position: 'insideBottom', offset: -16, fontSize: 11, fill: '#94a3b8' }
              : undefined
          }
          stroke="rgba(255,255,255,0.2)"
        />
        <YAxis
          tick={{ fontSize: 11, fill: '#94a3b8' }}
          label={
            yAxisLabel
              ? { value: yAxisLabel, angle: -90, position: 'insideLeft', fontSize: 11, fill: '#94a3b8' }
              : undefined
          }
          stroke="rgba(255,255,255,0.2)"
        />
        <Tooltip
          contentStyle={{
            borderRadius: '8px',
            fontSize: '12px',
            border: '1px solid rgba(255,255,255,0.15)',
            background: 'rgba(15, 15, 30, 0.95)',
            color: '#ffffff',
            backdropFilter: 'blur(8px)',
          }}
        />
        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function PieChartWidget({ data }: { data: RechartsData[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="label"
          cx="50%"
          cy="50%"
          outerRadius={90}
          label={({ label, percent }) =>
            `${label} ${(percent * 100).toFixed(0)}%`
          }
          labelLine={true}
        >
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            borderRadius: '8px',
            fontSize: '12px',
            border: '1px solid rgba(255,255,255,0.15)',
            background: 'rgba(15, 15, 30, 0.95)',
            color: '#ffffff',
            backdropFilter: 'blur(8px)',
          }}
        />
        <Legend wrapperStyle={{ fontSize: '12px' }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

function RadarChartWidget({ data }: { data: RechartsData[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <RadarChart data={data} cx="50%" cy="50%" outerRadius={90}>
        <PolarGrid className="stroke-border/50" />
        <PolarAngleAxis dataKey="label" tick={{ fontSize: 11 }} />
        <Radar
          dataKey="value"
          stroke={DEFAULT_COLORS[0]}
          fill={DEFAULT_COLORS[0]}
          fillOpacity={0.35}
        />
        <Tooltip
          contentStyle={{
            borderRadius: '8px',
            fontSize: '12px',
            border: '1px solid rgba(255,255,255,0.15)',
            background: 'rgba(15, 15, 30, 0.95)',
            color: '#ffffff',
            backdropFilter: 'blur(8px)',
          }}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}

function LineChartWidget({
  data,
  xAxisLabel,
  yAxisLabel,
}: {
  data: RechartsData[];
  xAxisLabel?: string;
  yAxisLabel?: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 24 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11, fill: '#94a3b8' }}
          label={
            xAxisLabel
              ? { value: xAxisLabel, position: 'insideBottom', offset: -16, fontSize: 11, fill: '#94a3b8' }
              : undefined
          }
          stroke="rgba(255,255,255,0.2)"
        />
        <YAxis
          tick={{ fontSize: 11, fill: '#94a3b8' }}
          label={
            yAxisLabel
              ? { value: yAxisLabel, angle: -90, position: 'insideLeft', fontSize: 11, fill: '#94a3b8' }
              : undefined
          }
          stroke="rgba(255,255,255,0.2)"
        />
        <Tooltip
          contentStyle={{
            borderRadius: '8px',
            fontSize: '12px',
            border: '1px solid rgba(255,255,255,0.15)',
            background: 'rgba(15, 15, 30, 0.95)',
            color: '#ffffff',
            backdropFilter: 'blur(8px)',
          }}
        />
        <Line
          type="monotone"
          dataKey="value"
          stroke={DEFAULT_COLORS[0]}
          strokeWidth={2}
          dot={{ r: 4, fill: DEFAULT_COLORS[0] }}
          activeDot={{ r: 6 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export default function AiSdkChartWidget({
  title,
  chartType,
  data,
  xAxisLabel,
  yAxisLabel,
}: ChartConfig) {
  const rechartsData = toRechartsData(data);

  return (
    <div className="border-border bg-card my-2 w-full rounded-xl border p-4 shadow-sm">
      {title && (
        <p className="text-foreground mb-3 text-sm font-semibold">{title}</p>
      )}
      {chartType === 'bar' && (
        <BarChartWidget
          data={rechartsData}
          xAxisLabel={xAxisLabel}
          yAxisLabel={yAxisLabel}
        />
      )}
      {chartType === 'pie' && <PieChartWidget data={rechartsData} />}
      {chartType === 'radar' && <RadarChartWidget data={rechartsData} />}
      {chartType === 'line' && (
        <LineChartWidget
          data={rechartsData}
          xAxisLabel={xAxisLabel}
          yAxisLabel={yAxisLabel}
        />
      )}
    </div>
  );
}
