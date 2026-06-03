import type { Alarm, EventLog, WorkOrder, Workshop } from './types'

export const controlServices = [
  {
    code: 'AI-DIAG-01',
    name: 'AI 诊断节点',
    role: 'DeepSeek 网关 / 诊断结果标准化',
    status: 'online',
    metric: '2 个待处理案例',
    boundary: '仅提供建议，高风险动作必须审批'
  },
  {
    code: 'PLAN-01',
    name: '生产计划节点',
    role: '产能平衡 / 工艺路线调整',
    status: 'online',
    metric: '1 个重排待审批',
    boundary: '未获调度审批前不得执行'
  },
  {
    code: 'MARKET-01',
    name: '市场模拟节点',
    role: '需求指数 / 价格压力信号',
    status: 'online',
    metric: '需求 +12%',
    boundary: '只输入计划器，不直接修改工单'
  },
  {
    code: 'NATS-01',
    name: '消息总线',
    role: '指标、报警、命令、生产事件',
    status: 'degraded',
    metric: 'MILL-02 同步延迟',
    boundary: '隔离期间保留应急通道'
  }
] as const

export const aiCoordination = {
  node: 'AI-DIAG-01',
  model: 'DeepSeek v4 pro',
  mode: '辅助决策',
  queue: [
    {
      caseId: 'CASE-1042',
      target: 'MILL-02',
      task: '主轴热故障诊断',
      status: '等待审批',
      confidence: 82
    },
    {
      caseId: 'CASE-1041',
      target: 'GRIND-01',
      task: '刀具磨损趋势检查',
      status: '持续监控',
      confidence: 74
    }
  ],
  approvals: [
    '节点隔离需要车间主管确认',
    '调度变更需要计划规则校验',
    'AI 输出必须先写入审计日志，再允许人工操作'
  ],
  coordinationLinks: [
    { from: '规则引擎', to: 'AI 诊断', state: '2 个活动触发器' },
    { from: 'AI 诊断', to: '生产计划', state: '1 个重排建议' },
    { from: '生产计划', to: '操作员', state: '等待审批' }
  ]
} as const

export const workshops: Workshop[] = [
  {
    code: 'turning',
    name: '车削车间',
    node: 'turning-workshop-01',
    status: 'running',
    load: 72,
    machines: [
      {
        code: 'LATHE-01',
        name: '车床 01',
        type: '数控车削',
        state: 'running',
        workOrder: 'WO-20260530-001',
        process: '轴类粗车',
        output: 186,
        target: 240,
        yieldRate: 98.1,
        oee: 84,
        toolWear: 41,
        sync: 'online'
      },
      {
        code: 'LATHE-02',
        name: '车床 02',
        type: '数控车削',
        state: 'idle',
        workOrder: '待命',
        process: '等待工艺派发',
        output: 0,
        target: 120,
        yieldRate: 100,
        oee: 0,
        toolWear: 23,
        sync: 'online'
      }
    ]
  },
  {
    code: 'milling',
    name: '铣削车间',
    node: 'milling-workshop-01',
    status: 'fault',
    load: 91,
    machines: [
      {
        code: 'MILL-01',
        name: '铣床 01',
        type: '立式铣削',
        state: 'running',
        workOrder: 'WO-20260530-003',
        process: '法兰精铣',
        output: 74,
        target: 110,
        yieldRate: 96.4,
        oee: 77,
        toolWear: 58,
        sync: 'online'
      },
      {
        code: 'MILL-02',
        name: '铣床 02',
        type: '卧式铣削',
        state: 'fault',
        workOrder: 'WO-20260530-004',
        process: '粗铣加工',
        output: 39,
        target: 160,
        yieldRate: 91.2,
        oee: 42,
        toolWear: 76,
        sync: 'delayed',
        lastAlarm: '主轴温度过高'
      }
    ]
  },
  {
    code: 'grinding',
    name: '磨削车间',
    node: 'grinding-workshop-01',
    status: 'warning',
    load: 64,
    machines: [
      {
        code: 'GRIND-01',
        name: '磨床 01',
        type: '精密磨削',
        state: 'warning',
        workOrder: 'WO-20260530-002',
        process: '套筒精加工',
        output: 112,
        target: 150,
        yieldRate: 97.3,
        oee: 73,
        toolWear: 68,
        sync: 'online',
        lastAlarm: '砂轮磨损接近上限'
      },
      {
        code: 'GRIND-02',
        name: '磨床 02',
        type: '精密磨削',
        state: 'maintenance',
        workOrder: '维护',
        process: '计划点检',
        output: 0,
        target: 0,
        yieldRate: 100,
        oee: 0,
        toolWear: 12,
        sync: 'online'
      }
    ]
  }
]

export const workOrders: WorkOrder[] = [
  {
    id: 'WO-20260530-001',
    product: '传动轴',
    route: ['车削', '磨削', '检验'],
    priority: 'P1',
    quantity: 240,
    completed: 186,
    due: '16:30',
    status: 'in_progress'
  },
  {
    id: 'WO-20260530-002',
    product: '精密套筒',
    route: ['车削', '磨削', '检验'],
    priority: 'P2',
    quantity: 150,
    completed: 112,
    due: '18:00',
    status: 'in_progress'
  },
  {
    id: 'WO-20260530-003',
    product: '泵体法兰',
    route: ['铣削', '去毛刺', '检验'],
    priority: 'P1',
    quantity: 110,
    completed: 74,
    due: '15:20',
    status: 'scheduled'
  },
  {
    id: 'WO-20260530-004',
    product: '阀体',
    route: ['铣削', '磨削', '检验'],
    priority: 'P1',
    quantity: 160,
    completed: 39,
    due: '17:10',
    status: 'blocked'
  }
]

export const alarms: Alarm[] = [
  {
    id: 'ALM-0042',
    severity: 'high',
    machine: 'MILL-02',
    title: '主轴温度过高',
    value: '89 C / 阈值 82 C',
    status: 'diagnosed',
    rule: '刀具磨损与主轴温度连续 3 次采样超过联合阈值。',
    aiSuggestion:
      '可能由冷却液延迟与轴承摩擦叠加导致。建议暂停当前作业，将 WO-20260530-004 剩余产量转移到 MILL-01，并执行冷却回路检查。',
    requiredRole: '车间主管'
  },
  {
    id: 'ALM-0041',
    severity: 'medium',
    machine: 'GRIND-01',
    title: '砂轮磨损接近上限',
    value: '68% / 预警 65%',
    status: 'confirmed',
    rule: '砂轮磨损超过预警阈值，但良品率仍保持在 97% 以上。',
    aiSuggestion:
      '建议降低进给速度完成当前批次，并在下一个高精度套筒工单前安排砂轮更换。',
    requiredRole: '操作员'
  }
]

export const eventLogs: EventLog[] = [
  {
    time: '14:22:18',
    source: 'MILL-02',
    message: 'AI 诊断已关联到 ALM-0042',
    level: 'danger'
  },
  {
    time: '14:21:44',
    source: 'central-api',
    message: '调度规则建议重排 WO-20260530-004',
    level: 'warning'
  },
  {
    time: '14:20:39',
    source: 'MILL-02',
    message: '本地冷却检查完成，结果为预警',
    level: 'warning'
  },
  {
    time: '14:18:02',
    source: 'turning-workshop-01',
    message: '心跳与生产同步已接收',
    level: 'info'
  }
]

export const demoScenario = {
  edgeNode: {
    code: 'milling-workshop-01',
    role: '远程车间边缘节点',
    deployment: '云服务器 / Cloud Edge Node',
    heartbeat: '5 秒/次',
    localDb: 'SQLite 本地缓存',
    syncTarget: '中央控制 central-api'
  },
  normal: {
    title: '正常生产运行',
    summary: '云端车间节点持续模拟铣削生产，边缘节点本地记录生产数据并通过心跳同步到主机。',
    machineState: '运行中',
    aiState: '旁路监控',
    operatorAction: '无需人工介入',
    records: [
      'MILL-01 按 60 秒/件节拍生产泵体法兰',
      '刀具磨损随累计产量缓慢上升',
      '良品率保持在 96% 左右',
      '心跳包包含设备、生产、报警、同步状态摘要'
    ]
  },
  emergency: {
    title: '紧急异常处置',
    summary: 'MILL-02 连续 3 次采样出现主轴温度与刀具磨损联合越限，AI 弹窗引导人工确认与调度重排。',
    machineState: '故障',
    aiState: '主动引导',
    operatorAction: '确认报警、隔离节点、重排工单',
    records: [
      '规则引擎触发 SPINDLE_TEMP_HIGH',
      'AI 诊断判断冷却延迟叠加轴承摩擦风险',
      '系统建议暂停 MILL-02 并转移剩余工单',
      '高风险动作必须由车间主管批准并写入审计'
    ]
  },
  scientificBasis: [
    '使用公开 NASA Milling Wear 数据集的思路：不同转速、进给、切深下记录铣刀磨损 VB。',
    '采用刀具磨损、振动/负载、温度、良品率之间的因果约束，而不是独立随机数。',
    '状态机限制设备只能从运行进入预警、故障、维护或隔离，避免不真实跳变。'
  ]
} as const
