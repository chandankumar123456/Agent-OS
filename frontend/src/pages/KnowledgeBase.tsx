import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { apiClient } from '../api/client';
import { buttonTap } from '../lib/animations';
import { Upload, FileText, Trash2, Search, X } from 'lucide-react';
import { Skeleton } from '../components/ui/Skeleton';

interface Source {
 id: string;
 name: string;
 type: string;
 content_preview?: string;
 chunk_count: number;
 status: string;
 created_at: string;
}

interface Chunk {
 id: string;
 source_id: string;
 content: string;
 metadata?: any;
}

const KnowledgeBase = () => {
 const [sources, setSources] = useState<Source[]>([]);
 const [loading, setLoading] = useState(true);
 const [uploading, setUploading] = useState(false);
 const [error, setError] = useState('');
 const [selectedSource, setSelectedSource] = useState<Source | null>(null);
 const [query, setQuery] = useState('');
 const [queryResults, setQueryResults] = useState<Chunk[]>([]);
 const [querying, setQuerying] = useState(false);
 const fileInputRef = useRef<HTMLInputElement>(null);

 const load = async () => {
 try {
 const data = await apiClient.getKnowledgeSources();
 setSources(data);
 } catch (e: any) {
 setError(e.message);
 } finally {
 setLoading(false);
 }
 };

 useEffect(() => {
 load();
 }, []);

 const handleUpload = async (file: File) => {
 setUploading(true);
 setError('');
 try {
 await apiClient.uploadDocument(file);
 await load();
 } catch (e: any) {
 setError(e.message);
 } finally {
 setUploading(false);
 }
 };

 const handleDelete = async (id: string) => {
 try {
 await apiClient.deleteKnowledgeSource(id);
 await load();
 if (selectedSource?.id === id) {
 setSelectedSource(null);
 setQueryResults([]);
 }
 } catch (e: any) {
 setError(e.message);
 }
 };

 const runQuery = async () => {
 if (!selectedSource || !query.trim()) return;
 setQuerying(true);
 try {
 const res = await apiClient.queryKnowledge(selectedSource.id, query.trim());
 setQueryResults(res.chunks);
 } catch (e: any) {
 setError(e.message);
 } finally {
 setQuerying(false);
 }
 };

 return (
 <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-10 max-w-6xl mx-auto">
 <div className="flex items-end justify-between">
 <div>
 <h1 className="text-4xl font-pixel uppercase tracking-tight mb-2">Knowledge Archive</h1>
 <p className="text-secondaryText text-xl font-retro uppercase opacity-60">Neural context ingestion and indexing system.</p>
 </div>
 </div>

 {error && (
 <div className="p-4 border-4 border-[#FF4B4B]/20 bg-[#FF4B4B]/10 font-retro text-lg text-[#FF4B4B] flex items-center justify-between uppercase">
 <span>!! ERR: {error}</span>
 <motion.button whileTap={{ scale: 0.85 }} onClick={() => setError('')} className="border-4 border-[#FF4B4B] p-1">
 <X className="w-4 h-4" />
 </motion.button>
 </div>
 )}

 <motion.div
 className="border-4 border-dashed border-outline/30 p-8 text-center bg-white cursor-pointer shadow-pixel hover:bg-surface-high"
 onClick={() => fileInputRef.current?.click()}
 onDragOver={(e) => e.preventDefault()}
 onDrop={(e) => {
 e.preventDefault();
 const file = e.dataTransfer.files[0];
 if (file) handleUpload(file);
 }}
 {...buttonTap}
 animate={uploading ? { opacity: [0.7, 1, 0.7], borderColor: ['#FF6B35', '#000000', '#FF6B35'] } : {}}
 >
 <input
 ref={fileInputRef}
 type="file"
 accept=".pdf,.txt,.md"
 className="hidden"
 onChange={(e) => {
 const file = e.target.files?.[0];
 if (file) handleUpload(file);
 }}
 />
 <motion.div
 animate={uploading ? {} : { y: [0, -6, 0] }}
 transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
 className="inline-block"
 >
 <Upload className="w-12 h-12 text-primary mx-auto mb-4" />
 </motion.div>
 <p className="text-[10px] font-pixel uppercase text-secondaryText">
 {uploading ? '[ INGESTING_DATA... ]' : '[ CLICK_OR_DRAG_TO_ARCHIVE_PDF_TXT_MD ]'}
 </p>
 </motion.div>

 {loading ? (
 <div className="text-center py-8"><Skeleton className="h-4 w-32 mx-auto" /></div>
 ) : (
 <div className="pixel-panel overflow-hidden">
 <table className="w-full text-left">
 <thead className="border-b-4 border-outline bg-surface-high text-secondaryText text-[10px] font-pixel uppercase tracking-tighter">
 <tr>
 <th className="px-6 py-4 font-normal">Dataset_Label</th>
 <th className="px-6 py-4 font-normal">Format</th>
 <th className="px-6 py-4 font-normal">Chunk_Count</th>
 <th className="px-6 py-4 font-normal">Status</th>
 <th className="px-6 py-4 font-normal text-right">Link</th>
 </tr>
 </thead>
 <tbody className="text-lg font-retro uppercase text-primaryText">
 {sources.map((s, index) => (
 <motion.tr
 key={s.id}
 initial={{ opacity: 0 }}
 animate={{ opacity: 1 }}
 transition={{ delay: index * 0.05 }}
 className={`border-b-4 border-outline/5 hover:bg-surface-high cursor-pointer ${selectedSource?.id === s.id ? 'bg-primary/5' : ''}`}
 onClick={() => setSelectedSource(s)}
 >
 <td className="px-6 py-6 flex items-center gap-3">
 <FileText className="w-5 h-5 text-primary" />
 {s.name}
 </td>
 <td className="px-6 py-6 text-secondaryText">{s.type}</td>
 <td className="px-6 py-6">{s.chunk_count}</td>
 <td className="px-6 py-6">
 <span className="px-4 py-1 border-4 border-outline bg-secondary/10 text-secondary text-[8px] font-pixel uppercase">{s.status}</span>
 </td>
 <td className="px-6 py-6 text-right">
 <motion.button
 onClick={(e) => {
 e.stopPropagation();
 handleDelete(s.id);
 }}
 whileTap={{ scale: 0.85 }}
 className="text-secondaryText hover:text-[#FF4B4B] p-1 border-4 border-transparent hover:border-outline"
 >
 <Trash2 className="w-4 h-4" />
 </motion.button>
 </td>
 </motion.tr>
 ))}
 {sources.length === 0 && (
 <tr>
 <td colSpan={5} className="px-6 py-8 text-center text-secondaryText font-retro opacity-50">
 EMPTY_REGISTRY: NO DATASETS DETECTED.
 </td>
 </tr>
 )}
 </tbody>
 </table>
 </div>
 )}

 {selectedSource && (
 <div className="pixel-panel p-8 flex flex-col gap-8">
 <div className="flex items-center justify-between">
 <h2 className="text-xs font-pixel uppercase text-primary">{selectedSource.name}</h2>
 <button
 onClick={() => {
 setSelectedSource(null);
 setQueryResults([]);
 }}
 className="text-secondaryText hover:text-primary border-4 border-outline p-1"
 >
 <X className="w-5 h-5" />
 </button>
 </div>
 <div className="flex gap-4">
 <input
 type="text"
 className="flex-1 pixel-input text-lg font-retro uppercase"
 placeholder="Query latent space..."
 value={query}
 onChange={(e) => setQuery(e.target.value)}
 onKeyDown={(e) => e.key === 'Enter' && runQuery()}
 />
 <button
 onClick={runQuery}
 disabled={querying}
 className="btn-primary px-8 py-4 flex items-center gap-3 disabled:opacity-50"
 >
 <Search className="w-5 h-5" /> [ {querying ? 'INGRESSING...' : 'RUN_QUERY'} ]
 </button>
 </div>

 {queryResults.length > 0 && (
 <div className="flex flex-col gap-4">
 <p className="text-[10px] font-pixel uppercase tracking-widest text-secondaryText">Neural_Matches</p>
 <div className="grid grid-cols-1 gap-4">
 {queryResults.map((chunk) => (
 <motion.div
 key={chunk.id}
 initial={{ opacity: 0, x: -10 }}
 animate={{ opacity: 1, x: 0 }}
 className="p-6 border-4 border-outline bg-white font-retro text-lg leading-relaxed uppercase shadow-pixel"
 >
 {chunk.content}
 </motion.div>
 ))}
 </div>
 </div>
 )}
 </div>
 )}
 </motion.div>
 );
};

export default KnowledgeBase;
