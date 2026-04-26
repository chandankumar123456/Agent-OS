import React from 'react';
import type { VisibilityEvent } from '../../types/results';
import { BrowserResultCard } from './BrowserResultCard';
import { FileResultCard } from './FileResultCard';
import { DesktopResultCard } from './DesktopResultCard';
import { ShellResultCard } from './ShellResultCard';

interface Props { event: VisibilityEvent; }

export const ResultCard: React.FC<Props> = ({ event }) => {
  const v = event.visibility;
  if (!v) return null;
  const type = v.type;
  if (type?.startsWith('browser_')) return <BrowserResultCard visibility={v} />;
  if (type === 'file_operation') return <FileResultCard visibility={v} />;
  if (type?.startsWith('desktop_')) return <DesktopResultCard visibility={v} />;
  if (type === 'shell_output') return <ShellResultCard visibility={v} output={event.result?.output} />;
  return (
    <div className="rounded-lg border border-gray-200 p-4 bg-white">
      <p className="text-xs text-gray-500 mb-1">Unknown result type: {type}</p>
      <pre className="text-xs bg-gray-50 p-2 rounded">{JSON.stringify(v, null, 2)}</pre>
    </div>
  );
};
