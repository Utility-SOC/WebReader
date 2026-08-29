import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import RSVPDisplay from './components/RSVPDisplay';
import PdfManualEditor from './components/PdfManualEditor';
// ContextView import removed/unused in this cleanup to focus on core features, or can be re-added if essential
import ImageGallery from './components/ImageGallery';
import ChapterSelector from './components/ChapterSelector';
import AudioModal from './components/AudioModal';
import { Play, Pause, RotateCcw, Image, BookOpen, Volume2, Moon, Sun, ChevronLeft, ChevronRight, UploadCloud, FileText, X, Download } from 'lucide-react';
import { PRESETS, FONTS } from './constants';

const PREFS_KEY = "webreader:preferences:v1";

const loadPrefs = () => {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
};

function App() {
  const [words, setWords] = useState([]);
  const [images, setImages] = useState([]);
  const [index, setIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isDark, setIsDark] = useState(true);
  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [currentFile, setCurrentFile] = useState(null); // Track filename

  const savedPrefs = useRef(loadPrefs()).current;

  // Settings
  const [settings, setSettings] = useState(savedPrefs.settings || PRESETS.orp_focused.config);
  const [activePresetId, setActivePresetId] = useState(savedPrefs.activePresetId || 'orp_focused');

  // Appearance
  const [appearance, setAppearance] = useState({
    fontSize: 60,
    fontFamily: "'Courier New', monospace",
    containerWidth: 1024,
    orpColor: '#ef4444',
    textColor: '',
    ...savedPrefs.appearance
  });

  const timerRef = useRef(null);
  const [showEditor, setShowEditor] = useState(false);
  const [tempFile, setTempFile] = useState(null);

  // Chapter Selection State
  const [chapters, setChapters] = useState([]);
  const [showChapterSelector, setShowChapterSelector] = useState(false);
  const [showGallery, setShowGallery] = useState(false);
  const [showAudioModal, setShowAudioModal] = useState(false);
  const [manualBoxes, setManualBoxes] = useState(null);

  // Dynamic Punctuation State
  const [punctuationRules, setPunctuationRules] = useState(savedPrefs.punctuationRules || [
    { str: ".", val: 2.0 },
    { str: ",", val: 1.5 },
    { str: ";", val: 1.5 },
    { str: "?", val: 2.0 },
    { str: "!", val: 2.0 },
    { str: "—", val: 1.5 },
    { str: "\n\n", val: 3.0 }
  ]);

  // Persist reading/appearance preferences across reloads
  useEffect(() => {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify({ settings, appearance, punctuationRules, activePresetId }));
    } catch { /* localStorage unavailable (private mode, etc.) — settings just won't persist */ }
  }, [settings, appearance, punctuationRules, activePresetId]);

  const applyPreset = (id) => {
    setActivePresetId(id);
    setSettings(PRESETS[id].config);
  };

  // Quick punctuation-equalizer form (main-screen panel)
  const [newRuleStr, setNewRuleStr] = useState("");
  const [newRuleVal, setNewRuleVal] = useState(1.5);
  const addPunctuationRule = () => {
    if (!newRuleStr) return;
    setPunctuationRules(prev => [...prev, { str: newRuleStr, val: Number(newRuleVal) }]);
    setNewRuleStr("");
    setNewRuleVal(1.5);
  };
  const removePunctuationRule = (idx) => {
    setPunctuationRules(prev => prev.filter((_, i) => i !== idx));
  };

  // Handler for file upload
  // Return to the upload screen to load a different file (or redo the current
  // one with the other extraction mode — automatic vs. manual — since that
  // choice is only offered at upload time).
  const resetToUpload = () => {
    setWords([]);
    setImages([]);
    setChapters([]);
    setIndex(0);
    setIsPlaying(false);
    setLoading(false);
    setTaskId(null);
    setStatusMessage("");
    setCurrentFile(null);
    setTempFile(null);
    setManualBoxes(null);
  };

  const handleUpload = async (e) => {
    const selected = e.target.files[0];
    if (!selected) return;

    setCurrentFile(selected.name);

    // Reset previous state
    setWords([]);
    setImages([]);
    setChapters([]);
    setIndex(0);

    if (selected.name.toLowerCase().endsWith(".pdf")) {
      const confirmManual = window.confirm("Detected PDF. Do you want to use Manual Layout Extraction?\n\nOK = Manual Editor\nCancel = Automatic Import");
      if (confirmManual) {
        setLoading(true);
        setStatusMessage("Uploading for Manual Edit...");
        const formData = new FormData();
        formData.append("file", selected);
        try {
          const res = await fetch("/upload_temp", { method: "POST", body: formData });
          if (!res.ok) {
            const errText = await res.text();
            throw new Error(`Upload Failed (${res.status}): ${errText}`);
          }
          const data = await res.json();
          setTempFile(data);
          setManualBoxes(data.saved_boxes || {});
          setShowEditor(true);
        } catch (err) { alert(err.message); }
        finally { setLoading(false); setStatusMessage(""); }
        return;
      }
    }

    setLoading(true);
    setStatusMessage("Uploading & Starting Processing...");
    const formData = new FormData();
    formData.append("file", selected);
    try {
      const res = await fetch("/upload", { method: "POST", body: formData });
      if (!res.ok) throw new Error("Upload Failed");
      const data = await res.json();

      if (data.task_id) {
        setTaskId(data.task_id);
      } else {
        // Fallback sync
        setWords(data.words || []);
        setImages([]);
        setLoading(false);
      }
    } catch (err) { alert(err.message); setLoading(false); setStatusMessage(""); }
  };

  // Polling Effect
  useEffect(() => {
    let interval;
    if (loading && taskId) {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`/tasks/${taskId}`);
          if (!res.ok) return;
          const data = await res.json();

          if (data.status === "processing") {
            setStatusMessage("Processing document... This may take a moment.");
          } else if (data.status === "completed") {
            setWords(data.result.words || []);
            setImages(data.result.images || []);
            if (data.result.chapters?.length > 0) {
              setChapters(data.result.chapters);
              setShowChapterSelector(true);
            }
            setIndex(0);
            setIsPlaying(false);
            setLoading(false);
            setTaskId(null);
            setStatusMessage("");
            setManualBoxes(null);
          } else if (data.status === "failed") {
            alert("Processing Failed: " + data.error);
            setLoading(false);
            setTaskId(null);
          }
        } catch (err) { console.error(err); }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [loading, taskId]);

  // Spacebar Play/Pause
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (showEditor) return;
      const tag = document.activeElement?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.code === "Space") {
        e.preventDefault();
        setIsPlaying(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showEditor]);

  // Mouse Wheel Speed Control — scroll over the reader to speed up/slow down
  const readerCardRef = useRef(null);
  useEffect(() => {
    const el = readerCardRef.current;
    if (!el || showEditor) return;
    const handleWheel = (e) => {
      e.preventDefault();
      const delta = e.deltaY < 0 ? 10 : -10;
      setSettings(prev => ({ ...prev, wpm: Math.max(100, Math.min(1000, prev.wpm + delta)) }));
    };
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, [showEditor]);

  const handleManualFinish = async (boxesMap, startPage = 1) => {
    setShowEditor(false);
    setLoading(true);
    setStatusMessage("Processing with Manual Layout...");
    setManualBoxes(boxesMap); // Store for TTS usage later!
    try {
      const res = await fetch("/process_pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: tempFile.filename,
          manual_boxes: boxesMap,
          extract_images: true,
          start_page: startPage
        })
      });
      if (!res.ok) throw new Error("Processing Failed");
      const data = await res.json();
      setWords(data.words || []);
      setImages(data.images || []);
      setIndex(0);
    } catch (err) { alert(err.message); }
    finally { setLoading(false); setStatusMessage(""); }
  };

  // Download Transcript
  const downloadTranscript = () => {
    if (words.length === 0) return;
    const text = words.join(" ");
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = (currentFile ? currentFile + ".txt" : "transcript.txt");
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(url);
  };

  // Loop
  useEffect(() => {
    if (isPlaying && index < words.length) {
      const delay = (60000 / settings.wpm) * settings.chunkSize;
      let multiplier = 1;
      const word = words[index];

      if (word) {
        for (const rule of punctuationRules) {
          if (word.endsWith(rule.str) || (rule.str === "\\n\\n" && word === "\n\n")) {
            multiplier = rule.val;
            break;
          }
        }
        if (word.startsWith("[FIGURE")) multiplier = 4;
      }
      timerRef.current = setTimeout(() => setIndex(prev => prev + settings.chunkSize), delay * multiplier);
    }
    return () => clearTimeout(timerRef.current);
  }, [isPlaying, index, words, settings, punctuationRules]);


  if (showEditor && tempFile) {
    return <PdfManualEditor
      filename={tempFile.filename}
      pageCount={tempFile.page_count}
      initialBoxes={manualBoxes}
      onFinish={handleManualFinish}
      onCancel={() => { setShowEditor(false); setTempFile(null); setManualBoxes(null); }}
    />;
  }

  // --- UI RENDER ---

  const themeClasses = isDark
    ? "bg-[#0f1014] text-gray-100"
    : "bg-[#f8fafc] text-gray-900";

  const cardClasses = isDark
    ? "bg-[#181a20]/80 border-white/5 shadow-2xl shadow-black/40"
    : "bg-white/80 border-white/40 shadow-xl shadow-blue-500/5";

  return (
    <div className={`min-h-screen transition-colors duration-500 ${themeClasses} selection:bg-indigo-500/30 selection:text-indigo-200 overflow-x-hidden font-sans`}>

      {/* Background Ambience */}
      <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none">
        <div className={`absolute -top-40 -left-40 w-[600px] h-[600px] rounded-full blur-[120px] opacity-[0.15] mix-blend-screen animate-pulse ${isDark ? 'bg-indigo-600' : 'bg-blue-400'}`}></div>
        <div className={`absolute top-20 right-0 w-[500px] h-[500px] rounded-full blur-[100px] opacity-[0.1] mix-blend-screen ${isDark ? 'bg-purple-600' : 'bg-purple-400'}`}></div>
        <div className={`absolute bottom-0 left-1/3 w-[800px] h-[400px] rounded-full blur-[120px] opacity-[0.1] mix-blend-screen ${isDark ? 'bg-emerald-600' : 'bg-teal-400'}`}></div>
      </div>

      <div className="relative z-10 flex flex-col items-center w-full max-w-[1400px] mx-auto p-4 sm:p-6 lg:p-12 min-h-screen">

        {/* Header */}
        <header className="w-full flex justify-between items-center mb-12 sm:mb-16">
          <div className="flex items-center gap-4 group cursor-default">
            <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shadow-lg transition-transform group-hover:rotate-6 ${isDark ? 'bg-indigo-600 shadow-indigo-500/20' : 'bg-white shadow-blue-200'}`}>
              <span className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-indigo-600'}`}>W</span>
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">WebReader</h1>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button onClick={() => setIsDark(!isDark)} className={`p-3 rounded-full transition-all duration-300 ${isDark ? 'hover:bg-gray-800 text-yellow-400' : 'bg-white hover:bg-gray-100 text-gray-600 shadow-sm border border-gray-100'}`}>
              {isDark ? <Sun size={20} /> : <Moon size={20} />}
            </button>
          </div>
        </header>

        {/* Main Interface */}
        <main className="w-full flex-1 flex flex-col items-center justify-center gap-8 w-full max-w-5xl">

          <div ref={readerCardRef} className={`w-full relative rounded-[2.5rem] overflow-hidden backdrop-blur-xl border transition-all duration-500 ${cardClasses}`}>

            {/* Content Area */}
            <div className="min-h-[500px] flex flex-col items-center justify-center p-8 sm:p-12 relative">

              {loading ? (
                <div className="flex flex-col items-center justify-center gap-8 animate-in fade-in duration-700">
                  <div className="relative">
                    <div className="w-24 h-24 border-4 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin"></div>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="w-3 h-3 bg-indigo-500 rounded-full animate-pulse"></div>
                    </div>
                  </div>
                  <div className="text-center">
                    <h3 className="text-xl font-medium text-indigo-400 mb-2">{statusMessage}</h3>
                    <p className="text-sm opacity-50">Optimizing text extraction...</p>
                  </div>
                </div>
              ) : words.length === 0 ? (
                <div className="text-center space-y-8 max-w-lg mx-auto animate-in zoom-in-95 duration-500">
                  <div className="space-y-4">
                    <h2 className={`text-2xl font-semibold tracking-tight ${isDark ? 'text-white' : 'text-gray-900'}`}>
                      No document loaded
                    </h2>
                    <p className={`text-lg ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      Upload a file to begin reading.
                    </p>
                  </div>

                  <div className="pt-4">
                    <label className="group relative inline-flex flex-col items-center gap-4 cursor-pointer">
                      <div className={`w-full h-32 w-64 border-2 border-dashed rounded-2xl flex flex-col items-center justify-center gap-3 transition-all duration-300 group-hover:border-indigo-500/50 group-hover:bg-indigo-500/5 ${isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-300 bg-white/50'}`}>
                        <UploadCloud size={32} className={`transition-colors group-hover:text-indigo-500 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                        <span className="text-sm font-medium opacity-70 group-hover:opacity-100">Drop file or click to browse</span>
                      </div>
                      <input type="file" onChange={handleUpload} accept=".pdf,.epub,.mobi,.azw3,.txt,.docx,.png,.jpg,.jpeg,.webp" className="hidden" />
                    </label>
                    <p className="text-xs font-mono opacity-40 mt-6">SUPPORTS PDF, EPUB, MOBI, TXT, DOCX, IMAGES</p>
                  </div>
                </div>
              ) : (
                <div className="w-full h-full flex items-center justify-center cursor-pointer" onClick={() => setIsPlaying(!isPlaying)}>
                  <RSVPDisplay words={words} images={images} index={index} settings={settings} appearance={appearance} isDark={isDark} />
                </div>
              )}
            </div>

            {/* Control Bar (Only if loaded) */}
            {words.length > 0 && !loading && (
              <div className={`px-6 py-6 sm:px-10 sm:py-8 border-t backdrop-blur-md ${isDark ? 'bg-[#131418]/90 border-t-white/5' : 'bg-white/90 border-t-gray-100'}`}>

                {/* Progress */}
                <div className="mb-8 relative group">
                  <div className={`h-1.5 w-full rounded-full overflow-hidden ${isDark ? 'bg-gray-800' : 'bg-gray-200'}`}>
                    <div
                      className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-200 ease-linear"
                      style={{ width: `${(index / words.length) * 100}%` }}
                    ></div>
                  </div>
                  <input
                    type="range" min="0" max={words.length} value={index}
                    onChange={(e) => setIndex(Number(e.target.value))}
                    className="absolute inset-0 w-full h-4 -top-1 opacity-0 cursor-pointer"
                  />
                  <div className="flex justify-between mt-3 text-xs font-medium tracking-wider opacity-60 font-mono">
                    <span>{Math.floor((index / words.length) * 100)}%</span>
                    <span>{index.toLocaleString()} / {words.length.toLocaleString()}</span>
                  </div>
                </div>

                {/* Controls Grid */}
                <div className="grid grid-cols-3 items-center gap-4">

                  {/* Left Actions */}
                  <div className="flex items-center gap-2 justify-start">
                    <button onClick={resetToUpload} className={`p-2.5 rounded-xl transition-all ${isDark ? 'hover:bg-white/10 text-gray-400 hover:text-white' : 'hover:bg-gray-100 text-gray-500'}`} title="Load a Different File">
                      <UploadCloud size={20} />
                    </button>
                    <button onClick={() => setShowChapterSelector(true)} className={`p-2.5 rounded-xl transition-all ${isDark ? 'hover:bg-white/10 text-gray-400 hover:text-white' : 'hover:bg-gray-100 text-gray-500'}`} title="Chapters">
                      <BookOpen size={20} />
                    </button>
                    {images.length > 0 && (
                      <button onClick={() => setShowGallery(true)} className={`p-2.5 rounded-xl transition-all ${isDark ? 'hover:bg-white/10 text-gray-400 hover:text-white' : 'hover:bg-gray-100 text-gray-500'}`} title="Gallery">
                        <div className="relative">
                          <Image size={20} />
                          <span className="absolute -top-1 -right-1 w-2 h-2 bg-indigo-500 rounded-full"></span>
                        </div>
                      </button>
                    )}

                    {/* DOWNLOADS */}
                    <div className="flex gap-1 ml-2 pl-2 border-l border-white/10">
                      <button onClick={downloadTranscript} className={`p-2.5 rounded-xl transition-all ${isDark ? 'hover:bg-white/10 text-gray-400 hover:text-white' : 'hover:bg-gray-100 text-gray-500'}`} title="Download Transcript">
                        <FileText size={20} />
                      </button>
                      <button onClick={() => setShowAudioModal(true)} className={`p-2.5 rounded-xl transition-all ${isDark ? 'hover:bg-white/10 text-gray-400 hover:text-white' : 'hover:bg-gray-100 text-gray-500'}`} title="Download Audio (TTS)">
                        <Volume2 size={20} />
                      </button>
                    </div>
                  </div>

                  {/* Center Playback */}
                  <div className="flex items-center justify-center gap-6">
                    <button onClick={() => setIndex(Math.max(0, index - 50))} className={`p-3 rounded-full transition-all active:scale-90 ${isDark ? 'hover:bg-white/10 text-gray-300' : 'hover:bg-gray-100 text-gray-600'}`}>
                      <ChevronLeft size={24} />
                    </button>

                    <button
                      onClick={() => setIsPlaying(!isPlaying)}
                      className="group relative"
                    >
                      <div className={`absolute -inset-0.5 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-full blur opacity-60 group-hover:opacity-100 transition duration-300`}></div>
                      <div className={`relative w-16 h-16 rounded-full flex items-center justify-center shadow-2xl transition-transform active:scale-95 ${isDark ? 'bg-white text-black' : 'bg-gray-900 text-white'}`}>
                        {isPlaying ? <Pause size={28} fill="currentColor" /> : <Play size={28} fill="currentColor" className="ml-1" />}
                      </div>
                    </button>

                    <button onClick={() => setIndex(Math.min(words.length, index + 50))} className={`p-3 rounded-full transition-all active:scale-90 ${isDark ? 'hover:bg-white/10 text-gray-300' : 'hover:bg-gray-100 text-gray-600'}`}>
                      <ChevronRight size={24} />
                    </button>
                  </div>

                  {/* Right Actions */}
                  <div className="flex items-center gap-2 justify-end">
                    <button onClick={() => setIndex(0)} className={`p-2.5 rounded-xl transition-all ${isDark ? 'hover:bg-white/10 text-gray-400 hover:text-white' : 'hover:bg-gray-100 text-gray-500'}`} title="Restart">
                      <RotateCcw size={20} />
                    </button>
                  </div>

                </div>
              </div>
            )}
          </div>

          {/* Settings — all on the front page, each pane collapsible */}
          <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-6">
            <details open className={`rounded-2xl border p-5 ${cardClasses}`}>
              <summary className="font-semibold mb-3 cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden flex items-center justify-between">
                Reading Presets <span className="text-xs opacity-40">▾</span>
              </summary>
              <div className="space-y-2 mt-3">
                {Object.values(PRESETS).map((preset) => (
                  <button
                    key={preset.id}
                    onClick={() => applyPreset(preset.id)}
                    className={`w-full text-left p-3 rounded-xl transition-all border ${
                      activePresetId === preset.id
                        ? (isDark ? 'border-indigo-500 bg-indigo-500/10' : 'border-indigo-400 bg-indigo-50')
                        : (isDark ? 'border-transparent hover:bg-white/5' : 'border-transparent hover:bg-gray-50')
                    }`}
                  >
                    <div className="font-medium text-sm">{preset.label}</div>
                    <div className="text-xs opacity-50">{preset.citation}</div>
                  </button>
                ))}
              </div>
            </details>

            <details open className={`rounded-2xl border p-5 ${cardClasses}`}>
              <summary className="font-semibold mb-3 cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden flex items-center justify-between">
                Appearance <span className="text-xs opacity-40">▾</span>
              </summary>
              <div className="mt-3">
                <label className="block text-xs opacity-70 mb-1">Font</label>
                <select
                  value={appearance.fontFamily}
                  onChange={(e) => setAppearance({ ...appearance, fontFamily: e.target.value })}
                  className={`w-full p-2 rounded-lg border text-sm mb-4 ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-white border-gray-200'}`}
                >
                  {FONTS.map(f => <option key={f.name} value={f.family}>{f.label}</option>)}
                </select>
                <div className="grid grid-cols-2 gap-4 mb-4">
                  <div>
                    <div className="flex justify-between text-xs opacity-70 mb-1"><span>Size</span><span>{appearance.fontSize}px</span></div>
                    <input type="range" min="24" max="120" value={appearance.fontSize} onChange={(e) => setAppearance({ ...appearance, fontSize: Number(e.target.value) })} className="w-full" />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs opacity-70 mb-1"><span>Width</span><span>{appearance.containerWidth}px</span></div>
                    <input type="range" min="400" max="1400" step="20" value={appearance.containerWidth} onChange={(e) => setAppearance({ ...appearance, containerWidth: Number(e.target.value) })} className="w-full" />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-xs opacity-70 mb-1">
                    <span>Text Color</span>
                    {appearance.textColor && <button onClick={() => setAppearance({ ...appearance, textColor: '' })} className="text-indigo-400 hover:underline">Reset to theme</button>}
                  </div>
                  <div className="flex items-center gap-3">
                    <input
                      type="color"
                      value={appearance.textColor || (isDark ? '#f3f4f6' : '#111827')}
                      onChange={(e) => setAppearance({ ...appearance, textColor: e.target.value })}
                      className="h-9 w-14 rounded cursor-pointer bg-transparent border border-gray-500/30"
                    />
                    <span className="text-xs opacity-50">{appearance.textColor || 'Using theme default'}</span>
                  </div>
                </div>
              </div>
            </details>

            <details open className={`rounded-2xl border p-5 ${cardClasses}`}>
              <summary className="font-semibold mb-3 cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden flex items-center justify-between">
                Mechanics <span className="text-xs opacity-40">▾</span>
              </summary>
              <div className="space-y-4 mt-3">
                <div>
                  <div className="flex justify-between text-xs opacity-70 mb-1"><span>Speed</span><span className="text-indigo-400 font-mono">{settings.wpm} WPM</span></div>
                  <input type="range" min="100" max="900" step="10" value={settings.wpm} onChange={(e) => setSettings({ ...settings, wpm: Number(e.target.value) })} className="w-full" />
                  <div className="text-xs opacity-40 mt-1">Or scroll over the reader above to adjust speed.</div>
                </div>
                <div>
                  <div className="flex justify-between text-xs opacity-70 mb-1"><span>Chunk Size</span><span className="text-indigo-400 font-mono">{settings.chunkSize} Words</span></div>
                  <input type="range" min="1" max="6" step="1" value={settings.chunkSize} onChange={(e) => setSettings({ ...settings, chunkSize: Number(e.target.value) })} className="w-full" />
                </div>
                <div>
                  <div className="flex justify-between text-xs opacity-70 mb-1"><span>ORP Pivot Position</span><span className="text-indigo-400 font-mono">{Math.round(settings.orpOffset * 100)}%</span></div>
                  <input type="range" min="0.1" max="0.9" step="0.05" value={settings.orpOffset} onChange={(e) => setSettings({ ...settings, orpOffset: Number(e.target.value) })} className="w-full" />
                </div>
                <div>
                  <div className="text-xs opacity-70 mb-1">ORP Highlight Color</div>
                  <div className="flex items-center gap-3">
                    <input
                      type="color"
                      value={appearance.orpColor}
                      onChange={(e) => setAppearance({ ...appearance, orpColor: e.target.value })}
                      className="h-9 w-14 rounded cursor-pointer bg-transparent border border-gray-500/30"
                    />
                    <span className="text-xs opacity-50">Red is the common convention (strongest contrast against body text); pick whatever reads best for you.</span>
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-1">
                  <label className={`flex items-center gap-2 cursor-pointer select-none p-2.5 rounded-lg text-sm ${isDark ? 'bg-black/20 hover:bg-black/30' : 'bg-gray-50 hover:bg-gray-100'}`}>
                    <input type="checkbox" checked={settings.guideLines} onChange={e => setSettings({ ...settings, guideLines: e.target.checked })} /> Guide Lines
                  </label>
                  <label className={`flex items-center gap-2 cursor-pointer select-none p-2.5 rounded-lg text-sm ${isDark ? 'bg-black/20 hover:bg-black/30' : 'bg-gray-50 hover:bg-gray-100'}`}>
                    <input type="checkbox" checked={settings.bionicBolding} onChange={e => setSettings({ ...settings, bionicBolding: e.target.checked })} /> Bionic Bolding
                  </label>
                  <label className={`flex items-center gap-2 cursor-pointer select-none p-2.5 rounded-lg text-sm ${isDark ? 'bg-black/20 hover:bg-black/30' : 'bg-gray-50 hover:bg-gray-100'}`}>
                    <input type="checkbox" checked={settings.orpCentering} onChange={e => setSettings({ ...settings, orpCentering: e.target.checked })} /> Force ORP Centering
                  </label>
                </div>
              </div>
            </details>

            <details open className={`rounded-2xl border p-5 ${cardClasses}`}>
              <summary className="font-semibold mb-3 cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden flex items-center justify-between">
                Punctuation <span className="text-xs opacity-40">▾</span>
              </summary>
              <div className="mt-3">
                <div className="text-xs opacity-70 mb-2">Delay multipliers for pacing.</div>
                <div className="space-y-1 mb-4 max-h-48 overflow-y-auto">
                  {punctuationRules.map((rule, i) => (
                    <div key={i} className={`flex justify-between items-center text-sm p-2 rounded-lg ${isDark ? 'bg-black/20' : 'bg-gray-50'}`}>
                      <span className="font-mono opacity-80">"{rule.str === "\n\n" ? "¶" : rule.str}"</span>
                      <span className="font-bold text-indigo-400">{rule.val}x</span>
                      <button onClick={() => removePunctuationRule(i)} className="text-red-500 hover:text-red-400 font-bold px-2">×</button>
                    </div>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input placeholder="String" value={newRuleStr} onChange={e => setNewRuleStr(e.target.value)} className={`w-20 p-2 text-sm rounded-lg border ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-white border-gray-200'}`} />
                  <input type="number" step="0.1" value={newRuleVal} onChange={e => setNewRuleVal(e.target.value)} className={`w-16 p-2 text-sm rounded-lg border ${isDark ? 'bg-gray-900 border-gray-700' : 'bg-white border-gray-200'}`} />
                  <button onClick={addPunctuationRule} className="flex-1 px-3 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-bold">ADD</button>
                </div>
              </div>
            </details>
          </div>
        </main>
      </div>

      {/* Modals */}
      {showChapterSelector && <ChapterSelector
        chapters={chapters}
        onSelect={(idx) => { setIndex(idx); setShowChapterSelector(false); }}
        onClose={() => setShowChapterSelector(false)}
        isDark={isDark}
      />}

      {showGallery && <ImageGallery
        images={images}
        onClose={() => setShowGallery(false)}
        isDark={isDark}
      />}

      {showAudioModal && <AudioModal
        filename={tempFile?.filename || currentFile} // Pass current filename
        pageCount={tempFile?.page_count || 100}
        manualBoxes={manualBoxes}
        onCancel={() => setShowAudioModal(false)}
      />}

    </div>
  );
}

export default App;
