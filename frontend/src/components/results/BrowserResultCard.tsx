import React from 'react';
import type { VisibilityPayload } from '../../types/results';

interface Props { visibility: VisibilityPayload; }

export const BrowserResultCard: React.FC<Props> = ({ visibility }) => {
  const { url, title, path, query, domain, selector } = visibility;
  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-blue-600 font-semibold text-sm">Browser</span>
        {url && (
          <a href={url} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline text-sm truncate max-w-xs">
            {title || url}
          </a>
        )}
      </div>
      {query && <p className="text-sm text-gray-700">Searched: &ldquo;{query}&rdquo; {domain && `on ${domain}`}</p>}
      {selector && <p className="text-sm text-gray-700">Selector: <code>{selector}</code></p>}
      {path && (
        <div className="mt-2">
          <p className="text-xs text-gray-500 mb-1">Screenshot:</p>
          <img src={`file://${path}`} alt="Screenshot" className="max-w-full h-auto rounded border max-h-64" />
        </div>
      )}
    </div>
  );
};
