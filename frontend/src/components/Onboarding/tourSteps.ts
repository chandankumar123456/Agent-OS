export const dashboardTourSteps = [
  {
    id: 'task-form',
    attachTo: { element: '#dashboard-task-form', on: 'bottom' as const },
    title: 'Submit a Task',
    text: 'Enter any query here and choose an execution mode. Try "Research AI trends" to get started.',
  },
  {
    id: 'metrics',
    attachTo: { element: '#metrics-panel', on: 'left' as const },
    title: 'Live Metrics',
    text: 'Track system health, task counts, and performance in real time.',
  },
  {
    id: 'recent-tasks',
    attachTo: { element: '#recent-tasks-panel', on: 'top' as const },
    title: 'Recent Tasks',
    text: 'View your latest tasks, their status, and quick results.',
  },
];

export const agentBuilderTourSteps = [
  {
    id: 'templates',
    attachTo: { element: '#agent-templates', on: 'right' as const },
    title: 'Agent Templates',
    text: 'Start with a template or build from scratch.',
  },
  {
    id: 'identity',
    attachTo: { element: '#agent-identity', on: 'bottom' as const },
    title: 'Agent Identity',
    text: 'Define name, role, goal, and backstory to shape behavior.',
  },
  {
    id: 'test-panel',
    attachTo: { element: '#agent-test-panel', on: 'left' as const },
    title: 'Test Panel',
    text: 'Run your agent against sample inputs and iterate quickly.',
  },
];

export const workflowBuilderTourSteps = [
  {
    id: 'node-palette',
    attachTo: { element: '#workflow-node-palette', on: 'right' as const },
    title: 'Node Palette',
    text: 'Drag agent, tool, decision, and approval nodes onto the canvas.',
  },
  {
    id: 'canvas',
    attachTo: { element: '#workflow-canvas', on: 'bottom' as const },
    title: 'Canvas',
    text: 'Connect nodes to build your pipeline. Click edges to configure.',
  },
  {
    id: 'execute',
    attachTo: { element: '#workflow-execute-btn', on: 'left' as const },
    title: 'Execute Workflow',
    text: 'Save and run your workflow. Monitor execution in real time.',
  },
];
