import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Table, Button, Space, Tag, Modal, Form, Input, Select, App, Badge,
} from 'antd';
import {
  PlusOutlined, PlayCircleOutlined, StopOutlined, EyeOutlined, BarChartOutlined,
} from '@ant-design/icons';
import type { Experiment } from '../../api/types';
import { useExperimentStore } from '../../store/experimentStore';
import { useTargetStore } from '../../store/targetStore';
import { formatDateTime } from '../../utils/formatters';
import {
  AttackFamilyLabel, DefenseLayerLabel, ExperimentStatus as ExpStatus,
} from '../../utils/constants';
import { experimentStatusColor, attackFamilyColor } from '../../utils/colorMap';

const statusLabel: Record<string, string> = {
  draft: '草稿', pending: '等待中', running: '运行中',
  completed: '已完成', failed: '失败', stopped: '已停止',
};

export default function ExperimentCenter() {
  const navigate = useNavigate();
  const { message: msg } = App.useApp();
  const { experiments, loading, fetchExperiments, createExperiment, startExperiment, stopExperiment } = useExperimentStore();
  const { targets, fetchTargets } = useTargetStore();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    fetchExperiments();
    fetchTargets();
  }, []);

  const handleCreate = async () => {
    const values = await form.validateFields();
    await createExperiment(values);
    msg.success('实验创建成功');
    setModalOpen(false);
    form.resetFields();
  };

  const handleStart = async (runId: string) => {
    await startExperiment(runId);
    msg.success('实验已启动');
  };

  const handleStop = async (runId: string) => {
    await stopExperiment(runId);
    msg.warning('实验已停止');
  };

  const columns = [
    { title: '实验ID', dataIndex: 'run_id', key: 'run_id', width: 160, render: (id: string) => <code>{id}</code> },
    { title: '名称', dataIndex: 'name', key: 'name', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (s: string) => {
        const isRunning = s === 'running';
        return (
          <Badge status={isRunning ? 'processing' : (s === 'completed' ? 'success' : (s === 'failed' ? 'error' : 'default'))}
            text={<Tag color={experimentStatusColor[s]}>{statusLabel[s] || s}</Tag>}
          />
        );
      },
    },
    {
      title: '测试目标', key: 'targets', width: 120,
      render: (_: unknown, r: Experiment) => (
        <Space size={[2, 2]} wrap>{r.target_ids.map((id) => <Tag key={id}>{id}</Tag>)}</Space>
      ),
    },
    {
      title: '攻击族', key: 'attacks', width: 200,
      render: (_: unknown, r: Experiment) => (
        <Space size={[2, 2]} wrap>
          {r.attack_families.map((f) => (
            <Tag key={f} color={attackFamilyColor[f]}>{AttackFamilyLabel[f].slice(0, 8)}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '进度', dataIndex: 'progress', key: 'progress', width: 100,
      render: (p?: { percentage: number }) => p ? `${p.percentage}%` : '-',
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: '操作', key: 'actions', width: 220, fixed: 'right' as const,
      render: (_: unknown, r: Experiment) => (
        <Space size={4}>
          {r.status === ExpStatus.DRAFT || r.status === ExpStatus.PENDING ? (
            <Button size="small" type="primary" icon={<PlayCircleOutlined />} onClick={() => handleStart(r.run_id)}>启动</Button>
          ) : null}
          {r.status === ExpStatus.RUNNING ? (
            <Button size="small" danger icon={<StopOutlined />} onClick={() => handleStop(r.run_id)}>停止</Button>
          ) : null}
          <Button size="small" icon={<EyeOutlined />} onClick={() => navigate(`/experiments/${r.run_id}`)}>详情</Button>
          {(r.status === ExpStatus.COMPLETED || r.status === ExpStatus.RUNNING) && (
            <Button size="small" icon={<BarChartOutlined />} onClick={() => navigate(`/results/${r.run_id}`)}>结果</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>实验编排中心</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          创建新实验
        </Button>
      </div>

      <Table
        dataSource={experiments}
        columns={columns}
        rowKey="run_id"
        loading={loading}
        scroll={{ x: 1200 }}
      />

      <Modal
        title="创建新实验"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleCreate}
        width={640}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="实验名称" rules={[{ required: true }]}>
            <Input placeholder="例如：第N轮：目标X-攻击族Y测试" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="target_ids" label="测试目标" rules={[{ required: true }]}>
            <Select mode="multiple" placeholder="选择Agent目标">
              {targets.map((t) => (
                <Select.Option key={t.id} value={t.id}>{t.name} ({t.id})</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="attack_families" label="攻击族" rules={[{ required: true }]}>
            <Select mode="multiple" placeholder="选择攻击类型（按Ctrl多选）">
              {Object.entries(AttackFamilyLabel).map(([k, v]) => (
                <Select.Option key={k} value={k}>{v}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="defense_layers" label="防御层">
            <Select mode="multiple" placeholder="选择启用的防御层（留空=全部启用）">
              {Object.entries(DefenseLayerLabel).map(([k, v]) => (
                <Select.Option key={k} value={k}>{v}</Select.Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
