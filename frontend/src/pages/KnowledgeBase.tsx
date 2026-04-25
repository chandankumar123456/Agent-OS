import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { apiClient } from '../api/client';
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
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-6 max-w-5xl mx-auto">
      <div className="flex items-end justify-between mb-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-1">Knowledge Base</h1>
          <p className="text-secondaryText text-sm">Upload documents and query chunks.</p>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-lg border border-[#FF4B4B]/20 bg-[#FF4B4B]/10 text-sm text-[#FF4B4B] flex items-center justify-between">
          <span>{error}</span>
          <motion.button whileTap={{ scale: 0.85 }} onClick={() => setError('')}>
            <X className="w-4 h-4" />
          </motion.button>
        </div>
      )}

      <motion.div
        className="border-2 border-dashed border-outline/20 rounded-xl p-8 text-center hover:border-primary/40 transition-colors cursor-pointer bg-surface-low"
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const file = e.dataTransfer.files[0];
          if (file) handleUpload(file);
        }}
        whileHover={{ borderColor: 'rgba(0,229,255,0.4)', scale: 1.01 }}
        animate={uploading ? { opacity: [0.7, 1, 0.7] } : {}}
        transition={{ repeat: Infinity, duration: 1.5 }}
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
          animate={uploading ? {} : { y: [0, -4, 0] }}
          transition={{ repeat: Infinity, duration: 2 }}
          className="inline-block"
        >
          <Upload className="w-8 h-8 text-secondaryText mx-auto mb-3" />
        </motion.div>
        <p className="text-sm text-secondaryText">{uploading ? 'Uploading...' : 'Click or drag & drop to upload PDF, TXT, or MD'}</p>
      </motion.div>

      {loading ? (
        <div className="text-center py-12"><Skeleton className="h-4 w-32 mx-auto" /></div>
      ) : (
        <div className="bg-surface-low border border-outline/20 rounded-xl overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-high text-secondaryText uppercase text-xs tracking-wider">
              <tr>
                <th className="px-6 py-3">Name</th>
                <th className="px-6 py-3">Type</th>
                <th className="px-6 py-3">Chunks</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline/10">
              {sources.map((s, index) => (
                <motion.tr
                  key={s.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: index * 0.05 }}
                  className={`hover:bg-surface-high/50 cursor-pointer ${selectedSource?.id === s.id ? 'bg-surface-high/30' : ''}`}
                  onClick={() => setSelectedSource(s)}
                >
                  <td className="px-6 py-4 flex items-center gap-2">
                    <FileText className="w-4 h-4 text-primary" />
                    {s.name}
                  </td>
                  <td className="px-6 py-4 capitalize">{s.type}</td>
                  <td className="px-6 py-4">{s.chunk_count}</td>
                  <td className="px-6 py-4">
                    <span className="px-2 py-1 rounded-full text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">{s.status}</span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <motion.button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(s.id);
                      }}
                      whileTap={{ scale: 0.85 }}
                      whileHover={{ scale: 1.1, color: '#FF4B4B' }}
                      className="text-secondaryText hover:text-[#FF4B4B] transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </motion.button>
                  </td>
                </motion.tr>
              ))}
              {sources.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-secondaryText">
                    No documents uploaded yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {selectedSource && (
        <div className="bg-surface-low border border-outline/20 rounded-xl p-6 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">{selectedSource.name}</h2>
            <motion.button
              onClick={() => {
                setSelectedSource(null);
                setQueryResults([]);
              }}
              whileTap={{ scale: 0.85 }}
              whileHover={{ scale: 1.1, rotate: 90 }}
              className="text-secondaryText hover:text-primaryText"
            >
              <X className="w-5 h-5" />
            </motion.button>
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              className="flex-1 bg-surface-high border border-outline/10 rounded-lg py-2 px-3 text-sm focus:outline-none focus:border-primary"
              placeholder="Search chunks..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && runQuery()}
            />
            <motion.button
              onClick={runQuery}
              disabled={querying}
              whileTap={{ scale: 0.96 }}
              whileHover={{ scale: 1.02 }}
              className="bg-primary hover:bg-primary/90 text-white px-4 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              <Search className="w-4 h-4" /> {querying ? 'Querying...' : 'Query'}
            </motion.button>
          </div>

          {queryResults.length > 0 && (
            <div className="flex flex-col gap-2 mt-2">
              <p className="text-xs uppercase tracking-wider text-secondaryText">Results</p>
              {queryResults.map((chunk) => (
                <motion.div
                  key={chunk.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="bg-surface-high border border-outline/10 rounded-lg p-3 text-sm"
                >
                  {chunk.content}
                </motion.div>
              ))}
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
};

export default KnowledgeBase;
