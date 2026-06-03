export type MachineState = 'running' | 'idle' | 'warning' | 'fault' | 'isolated' | 'maintenance'

export type Machine = {
  code: string
  name: string
  type: string
  state: MachineState
  workOrder: string
  process: string
  output: number
  target: number
  yieldRate: number
  oee: number
  toolWear: number
  sync: 'online' | 'delayed' | 'offline'
  lastAlarm?: string
}

export type Workshop = {
  code: string
  name: string
  node: string
  status: MachineState
  load: number
  machines: Machine[]
}

export type WorkOrder = {
  id: string
  product: string
  route: string[]
  priority: 'P1' | 'P2' | 'P3'
  quantity: number
  completed: number
  due: string
  status: 'scheduled' | 'in_progress' | 'blocked' | 'waiting'
}

export type Alarm = {
  id: string
  severity: 'medium' | 'high' | 'critical'
  machine: string
  title: string
  value: string
  status: 'unacknowledged' | 'confirmed' | 'diagnosed' | 'contained' | 'observing'
  rule: string
  aiSuggestion: string
  requiredRole: string
}

export type EventLog = {
  time: string
  source: string
  message: string
  level: 'info' | 'warning' | 'danger'
}
