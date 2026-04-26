import React from 'react';
import type { VisibilityPayload } from '../../types/results';

interface Props { visibility: VisibilityPayload; output?: string; }

export const ShellResultCard: React.FC<Props> = ({ visibility, output }) => {
  const { command } = visibility;
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-gray-600 font-semibold text-sm font-mono">Shell</span>
        {command && <code className="text-xs text-gray-500">{command}</code>}
      </div>
      {output && (
        <pre className="bg-black text-green-400 rounded px-3 py-2 text-xs overflow-auto max-h-48 border border-gray-700">
          {output}
        </pre>
      )}
    </div>
  );
};
