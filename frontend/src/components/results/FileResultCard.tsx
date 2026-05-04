import React from 'react';
import type { VisibilityPayload } from '../../types/results';

interface Props { visibility: VisibilityPayload; }

export const FileResultCard: React.FC<Props> = ({ visibility }) => {
 const { path, operation } = visibility;
 return (
 <div className="rounded-none border border-green-200 bg-green-50 p-4 shadow-sm">
 <div className="flex items-center gap-2 mb-2">
 <span className="text-green-600 font-semibold text-sm">File</span>
 {operation && <span className="text-xs text-gray-500">{operation}</span>}
 </div>
 <code className="block bg-white rounded-none px-4 py-2 text-sm text-gray-800 break-all border">{path}</code>
 <button
 onClick={() => {
 if (path) window.open(`file://${path}`, '_blank');
 }}
 className="mt-2 text-sm text-green-700 hover:text-green-900 font-medium underline"
 >
 Open file/folder
 </button>
 </div>
 );
};
