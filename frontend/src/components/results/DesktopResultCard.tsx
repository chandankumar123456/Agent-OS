import React from 'react';
import type { VisibilityPayload } from '../../types/results';

interface Props { visibility: VisibilityPayload; }

export const DesktopResultCard: React.FC<Props> = ({ visibility }) => {
 const { path, x, y, title, keys, amount } = visibility;
 return (
 <div className="rounded-none border border-purple-200 bg-purple-50 p-4 shadow-sm">
 <div className="flex items-center gap-2 mb-2">
 <span className="text-purple-600 font-semibold text-sm">Desktop</span>
 </div>
 {x !== undefined && y !== undefined && (
 <p className="text-sm text-gray-700">Clicked at ({x}, {y})</p>
 )}
 {keys && <p className="text-sm text-gray-700">Pressed: <code>{keys}</code></p>}
 {amount !== undefined && <p className="text-sm text-gray-700">Scrolled: {amount}</p>}
 {title && <p className="text-sm text-gray-700">Window: {title}</p>}
 {path && (
 <div className="mt-2">
 <p className="text-xs text-gray-500 mb-1">Screenshot:</p>
 <img src={`file://${path}`} alt="Screenshot" className="max-w-full h-auto rounded-none border max-h-64" />
 </div>
 )}
 </div>
 );
};
