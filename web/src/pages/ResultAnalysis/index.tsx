import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Row, Col, Descriptions, Tag, Table, Button, Space, Spin, Empty,
} from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type { EvaluationSummary, FamilyEvaluation, EvaluationTrendPoint } from '../../api/types';
import * as evaluationApi from '../../api/evaluation';
import { formatPercent, formatScore, formatDateTime } from '../../utils/formatters';
import { RiskLevelLabel } from '../../utils/constants';
import { riskLevelColor } from '../../utils/colorMap';

export default function ResultAnalysis() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<EvaluationSummary | null>(null);
  const [trend, setTrend] = useState<EvaluationTrendPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    Promise.all([
      evaluationApi.getEvaluationSummary(runId),
      evaluationApi.getTrend(runId),
    ]).then(([s, t]) => {
      setSummary(s);
      setTrend(t);
      setLoading(false);
    });
  }, [runId]);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!summary) return <Empty description="评估结果不存在" />;

  const familyList = Object.values(summary.by_family);

  // 各攻击族对比图
  const familyBarOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['ASR', 'DSR'] },
    grid: { left: 60, right: 20, top: 20, bottom: 100 },
    xAxis: {
      type: 'category',
      data: familyList.map((f) => f.label),
      axisLabel: { rotate: 45, fontSize: 10 },
    },
    yAxis: { type: 'value', max: 1, axisLabel: { formatter: (v: number) => formatPercent(v, 0) } },
    series: [
      { name: 'ASR', type: 'bar', data: familyList.map((f) => f.asr), itemStyle: { color: '#f5222d' } },
      { name: 'DSR', type: 'bar', data: familyList.map((f) => f.dsr), itemStyle: { color: '#52c41a' } },
    ],
  };

  // 趋势图
  const trendOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['ASR', 'DSR', 'H_cum (×10)'], bottom: 0 },
    grid: { left: 50, right: 50, top: 20, bottom: 40 },
    xAxis: {
      type: 'category',
      data: trend.map((p) => formatDateTime(p.timestamp).slice(11, 19)),
    },
    yAxis: { type: 'value', max: 1 },
    series: [
      { name: 'ASR', type: 'line', data: trend.map((p) => p.asr), smooth: true, itemStyle: { color: '#f5222d' } },
      { name: 'DSR', type: 'line', data: trend.map((p) => p.dsr), smooth: true, itemStyle: { color: '#52c41a' } },
      { name: 'H_cum (×10)', type: 'line', data: trend.map((p) => p.h_cum * 10), smooth: true, itemStyle: { color: '#faad14' }, lineStyle: { type: 'dashed' } },
    ],
  };

  const familyColumns = [
    {
      title: '攻击族', dataIndex: 'label', key: 'label', width: 150,
      render: (label: string, r: FamilyEvaluation) => (
        <Tag color={riskLevelColor[r.risk_level]}>{label}</Tag>
      ),
    },
    {
      title: 'ASR', dataIndex: 'asr', key: 'asr', width: 90,
      render: (v: number) => <span style={{ color: v > 0.5 ? '#f5222d' : '#52c41a' }}>{formatPercent(v)}</span>,
    },
    {
      title: 'DSR', dataIndex: 'dsr', key: 'dsr', width: 90,
      render: (v: number) => <span style={{ color: v > 0.5 ? '#52c41a' : '#faad14' }}>{formatPercent(v)}</span>,
    },
    {
      title: '风险评分', dataIndex: 'risk_score', key: 'risk_score', width: 120,
      render: (v: number, r: FamilyEvaluation) => (
        <Space>
          <span style={{ fontWeight: 600, color: riskLevelColor[r.risk_level] }}>{formatScore(v)}</span>
          <Tag color={riskLevelColor[r.risk_level]}>Lv.{r.risk_level}</Tag>
          <span style={{ fontSize: 11, color: '#999' }}>{RiskLevelLabel[r.risk_level]}</span>
        </Space>
      ),
    },
    { title: '样本数', dataIndex: 'sample_count', key: 'sample_count', width: 80 },
    { title: '成功数', dataIndex: 'success_count', key: 'success_count', width: 80 },
  ];

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/experiments')}>返回</Button>
        <h2 style={{ margin: 0 }}>评估结果分析</h2>
        <Tag color={riskLevelColor[summary.risk_level]}>
          综合风险 Lv.{summary.risk_level} ({RiskLevelLabel[summary.risk_level]})
        </Tag>
      </div>

      {/* 总览指标 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small"><Descriptions column={1} size="small" title="攻击效果">
            <Descriptions.Item label="ASR">{formatPercent(summary.asr)}</Descriptions.Item>
            <Descriptions.Item label="任务偏移率">{formatPercent(summary.task_drift_rate)}</Descriptions.Item>
            <Descriptions.Item label="拒答率">{formatPercent(summary.refusal_rate)}</Descriptions.Item>
          </Descriptions></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Descriptions column={1} size="small" title="防御效果">
            <Descriptions.Item label="DSR">{formatPercent(summary.dsr)}</Descriptions.Item>
            <Descriptions.Item label="误报率 (FPR)">{formatPercent(summary.fpr)}</Descriptions.Item>
            <Descriptions.Item label="漏报率 (FNR)">{formatPercent(summary.fnr)}</Descriptions.Item>
          </Descriptions></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Descriptions column={1} size="small" title="持续污染">
            <Descriptions.Item label="PRP">{formatPercent(summary.prp)}</Descriptions.Item>
            <Descriptions.Item label="BTR">{formatPercent(summary.btr)}</Descriptions.Item>
            <Descriptions.Item label="H_cum">{formatScore(summary.h_cum)}</Descriptions.Item>
          </Descriptions></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Descriptions column={1} size="small" title="综合">
            <Descriptions.Item label="风险评分">{formatScore(summary.risk_score)}</Descriptions.Item>
            <Descriptions.Item label="总攻击数">{summary.total_attacks}</Descriptions.Item>
            <Descriptions.Item label="实验ID"><code>{runId}</code></Descriptions.Item>
          </Descriptions></Card>
        </Col>
      </Row>

      {/* 图表 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card title="各攻击族 ASR / DSR 对比" size="small">
            <ReactECharts option={familyBarOption} style={{ height: 300 }} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="指标变化趋势" size="small">
            <ReactECharts option={trendOption} style={{ height: 300 }} />
          </Card>
        </Col>
      </Row>

      {/* 攻击族明细表 */}
      <Card title="按攻击族分拆指标" size="small">
        <Table dataSource={familyList} columns={familyColumns} rowKey="family" size="small" pagination={false} />
      </Card>
    </div>
  );
}
