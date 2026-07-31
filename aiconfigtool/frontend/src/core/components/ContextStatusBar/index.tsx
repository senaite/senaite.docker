import { useEffect, useState } from 'react';
import { Space, Tag, Typography } from 'antd';
import { CheckCircleFilled, CloudServerOutlined, RobotOutlined } from '@ant-design/icons';
import { useWorkspace } from '@/core/context/WorkspaceContext';
import { apiClient } from '@/core/services/apiClient';

const { Text } = Typography;

interface AiCfg {
  provider: string;
  ollama?: { model: string };
  cloud?: { provider: string; model: string };
}

export default function ContextStatusBar() {
  const { currentCompany } = useWorkspace();
  const [ai, setAi] = useState<AiCfg>({ provider: 'deterministic' });

  const load = () => apiClient.get<{ ai: AiCfg }>('/config/workspace')
    .then(c => setAi(c.ai)).catch(() => {});
  useEffect(() => { load(); }, []);

  // 监听设置页的实时切换
  useEffect(() => {
    const handler = (e: Event) => setAi((e as CustomEvent<AiCfg>).detail);
    window.addEventListener('aiconfig-changed', handler);
    return () => window.removeEventListener('aiconfig-changed', handler);
  }, []);

  let aiLabel = '未配置';
  let aiColor: string = 'default';
  if (ai.provider === 'deterministic') {
    aiLabel = '规则引擎（离线）'; aiColor = 'default';
  } else if (ai.provider === 'ollama') {
    aiLabel = ai.ollama?.model || 'Ollama'; aiColor = 'purple';
  } else if (ai.provider === 'cloud') {
    const p = ai.cloud?.provider || ''; const m = ai.cloud?.model || '';
    aiLabel = (p ? (p === 'deepseek' ? 'DeepSeek' : p === 'alibaba' ? '阿里百炼' : p === 'zhipu' ? '智谱' : p === 'moonshot' ? 'Kimi' : p === 'openai' ? 'OpenAI' : p) + ' · ' : '') + (m || 'Cloud API');
    aiColor = 'blue';
  }

  return (
    <div style={{ height: 32, lineHeight: '32px', padding: '0 16px', background: '#fff', borderTop: '1px solid #f0f0f0', display: 'flex', alignItems: 'center', fontSize: 12 }}>
      <Space size="large" split={<span style={{ color: '#d9d9d9' }}>|</span>}>
        <Space size={4}><CheckCircleFilled style={{ color: '#52c41a' }} /><Text type="secondary">就绪</Text></Space>
        <Space size={4}><CloudServerOutlined /><Text type="secondary">{currentCompany?.name ?? '未选择'}</Text></Space>
        <Space size={4}><RobotOutlined /><Text type="secondary">默认引擎：</Text><Tag color={aiColor} style={{ marginInlineStart: 0 }}>{aiLabel}</Tag><Text type="secondary" style={{ fontSize: 11 }}>（在设置页切换）</Text></Space>
      </Space>
    </div>
  );
}
