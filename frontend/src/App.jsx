import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import RSVPDisplay from './components/RSVPDisplay';
import PdfManualEditor from './components/PdfManualEditor';
// ContextView import removed/unused in this cleanup to focus on core features, or can be re-added if essential
import ImageGallery from './components/ImageGallery';
import ChapterSelector from './components/ChapterSelector';
import AudioModal from './components/AudioModal';
import SettingsModal from './components/SettingsModal';
import { Settings, Play, Pause, RotateCcw, Image, BookOpen, Volume2, Moon, Sun, ChevronLeft, ChevronRight, UploadCloud, FileText, X, Download } from 'lucide-react';
import { PRESETS } from './constants';

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

  // Settings
  const [settings, setSettings] = useState(PRESETS.orp_focused.config);

  // Appearance
  const [appearance, setAppearance] = useState({
    fontSize: 60,
    fontFamily: "'Courier New', monospace",
    containerWidth: 1024
  });

  const timerRef = useRef(null);
  const [showEditor, setShowEditor] = useState(false);
  const [tempFile, setTempFile] = useState(null);

  // Chapter Selection State
  const [chapters, setChapters] = useState([]);
  const [showChapterSelector, setShowChapterSelector] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showGallery, setShowGallery] = useState(false);
  const [showAudioModal, setShowAudioModal] = useState(false);
  const [manualBoxes, setManualBoxes] = useState(null);

  // Dynamic Punctuation State
  const [punctuationRules, setPunctuationRules] = useState([
    { str: ".", val: 2.0 },
    { str: ",", val: 1.5 },
    { str: ";", val: 1.5 },
    { str: "?", val: 2.0 },
    { str: "!", val: 2.0 },
    { str: "—", val: 1.5 },
    { str: "\n\n", val: 3.0 }
  ]);

  // Handler for file upload
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
            setStatusMessage("Processing PDF... This may take a moment.");
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
              <p className={`text-xs font-medium tracking-wide uppercase opacity-50 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Scientific Speed Reading</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button onClick={() => setIsDark(!isDark)} className={`p-3 rounded-full transition-all duration-300 ${isDark ? 'hover:bg-gray-800 text-yellow-400' : 'bg-white hover:bg-gray-100 text-gray-600 shadow-sm border border-gray-100'}`}>
              {isDark ? <Sun size={20} /> : <Moon size={20} />}
            </button>
            <button onClick={() => setShowSettings(true)} className={`p-3 rounded-full transition-all duration-300 ${isDark ? 'hover:bg-gray-800 text-gray-300 hover:text-white' : 'bg-white hover:bg-gray-100 text-gray-600 shadow-sm border border-gray-100'}`}>
              <Settings size={20} />
            </button>
          </div>
        </header>

        {/* Main Interface */}
        <main className="w-full flex-1 flex flex-col items-center justify-center gap-8 w-full max-w-5xl">

          <div className={`w-full relative rounded-[2.5rem] overflow-hidden backdrop-blur-xl border transition-all duration-500 ${cardClasses}`}>

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
                    <h2 className={`text-4xl sm:text-5xl font-bold tracking-tight ${isDark ? 'text-white' : 'text-gray-900'}`}>
                      Read Faster. <br /> <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">Learn More.</span>
                    </h2>
                    <p className={`text-lg ${isDark ? 'text-gray-400' : 'text-gray-600'}`}>
                      Upload your documents to experience improved comprehension with RSVP technology.
                    </p>
                  </div>

                  <div className="pt-4">
                    <label className="group relative inline-flex flex-col items-center gap-4 cursor-pointer">
                      <div className={`w-full h-32 w-64 border-2 border-dashed rounded-2xl flex flex-col items-center justify-center gap-3 transition-all duration-300 group-hover:border-indigo-500/50 group-hover:bg-indigo-500/5 ${isDark ? 'border-gray-700 bg-gray-800/50' : 'border-gray-300 bg-white/50'}`}>
                        <UploadCloud size={32} className={`transition-colors group-hover:text-indigo-500 ${isDark ? 'text-gray-500' : 'text-gray-400'}`} />
                        <span className="text-sm font-medium opacity-70 group-hover:opacity-100">Drop file or click to browse</span>
                      </div>
                      <input type="file" onChange={handleUpload} accept=".pdf,.epub,.txt,.docx,.png,.jpg,.jpeg,.webp" className="hidden" />
                    </label>
                    <p className="text-xs font-mono opacity-40 mt-6">SUPPORTS PDF, EPUB, TXT, DOCX, IMAGES</p>
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
        </main>
      </div>

      {/* Modals */}
      {showSettings && <SettingsModal
        settings={settings} setSettings={setSettings}
        appearance={appearance} setAppearance={setAppearance}
        punctuationRules={punctuationRules} setPunctuationRules={setPunctuationRules}
        onClose={() => setShowSettings(false)} isDark={isDark}
      />}

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
