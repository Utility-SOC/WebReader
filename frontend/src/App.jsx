import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import RSVPDisplay from './components/RSVPDisplay';
import PdfManualEditor from './components/PdfManualEditor';
import ContextView from './components/ContextView';
import ImageGallery from './components/ImageGallery';
import ChapterSelector from './components/ChapterSelector';
import AudioModal from './components/AudioModal';
import SettingsModal from './components/SettingsModal';
import { Settings, Play, Pause, RotateCcw, Image, BookOpen, Volume2, Moon, Sun, ChevronLeft, ChevronRight, Minus, Plus, X } from 'lucide-react';
import { FONTS, PRESETS } from './constants';


function App() {
  const [words, setWords] = useState([]);
  const [images, setImages] = useState([]);
  const [index, setIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isDark, setIsDark] = useState(true);
  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState(null);
  const [statusMessage, setStatusMessage] = useState("");

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

    if (selected.name.toLowerCase().endsWith(".pdf")) {
      const confirmManual = window.confirm("Detected PDF. Do you want to use Manual Layout Extraction?\n\nOK = Manual Editor\nCancel = Automatic Import");
      if (confirmManual) {
        setLoading(true);
        setStatusMessage("Uploading for Manual Edit...");
        const formData = new FormData();
        formData.append("file", selected);
        try {
          const res = await fetch("/upload_temp", { method: "POST", body: formData });
          const data = await res.json();
          setTempFile(data);
          if (data.saved_boxes) {
            setManualBoxes(data.saved_boxes);
          } else {
            setManualBoxes({});
          }
          setShowEditor(true);
          setLoading(false);
          setStatusMessage("");
        } catch (err) { alert(err); setLoading(false); setStatusMessage(""); }
        return;
      }
    }

    setLoading(true);
    setStatusMessage("Uploading & Starting Processing...");
    const formData = new FormData();
    formData.append("file", selected);
    try {
      // Use Async Upload
      const res = await fetch("/upload", { method: "POST", body: formData });
      const data = await res.json();

      if (data.task_id) {
        setTaskId(data.task_id);
        // loading stays true, polling effect will take over
      } else {
        // Fallback if sync (legacy)
        setWords(data.words || []);
        setImages([]);
        setIndex(0);
        setIsPlaying(false);
        setLoading(false);
        setStatusMessage("");
      }
    } catch (err) { alert(err); setLoading(false); setStatusMessage(""); }
  };

  // Polling Effect
  useEffect(() => {
    let interval;
    if (loading && taskId) {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`/tasks/${taskId}`);
          if (!res.ok) throw new Error("Status check failed");
          const data = await res.json();

          if (data.status === "processing") {
            setStatusMessage("Processing PDF... This may take a moment.");
          } else if (data.status === "completed") {
            setWords(data.result.words || []);
            setImages(data.result.images || []);
            if (data.result.chapters && data.result.chapters.length > 0) {
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
            setStatusMessage("");
          }
        } catch (err) {
          console.error("Polling error", err);
        }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [loading, taskId]);

  const handleManualFinish = async (boxesMap, startPage = 1) => {
    setShowEditor(false);
    setLoading(true);
    setManualBoxes(boxesMap);
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
      const data = await res.json();
      setWords(data.words || []);
      setImages(data.images || []);
      setIndex(0);
      setIsPlaying(false);
    } catch (err) { alert(err); }
    finally { setLoading(false); }
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
      boxes={manualBoxes}
      onSave={handleManualFinish}
      onCancel={() => { setShowEditor(false); setTempFile(null); setManualBoxes(null); }}
    />;
  }

  return (
    <div className={`min-h-screen transition-colors duration-500 ${isDark ? 'bg-gray-950 text-gray-100' : 'bg-gray-50 text-gray-900'} font-sans selection:bg-blue-500 selection:text-white`}>

      {/* Background Gradients */}
      <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none">
        <div className={`absolute -top-[10%] -left-[10%] w-[50%] h-[50%] rounded-full blur-[128px] opacity-20 ${isDark ? 'bg-blue-600' : 'bg-blue-400'}`}></div>
        <div className={`absolute top-[20%] -right-[10%] w-[40%] h-[40%] rounded-full blur-[128px] opacity-20 ${isDark ? 'bg-purple-600' : 'bg-purple-400'}`}></div>
        <div className={`absolute -bottom-[10%] left-[20%] w-[60%] h-[40%] rounded-full blur-[128px] opacity-10 ${isDark ? 'bg-teal-600' : 'bg-teal-400'}`}></div>
      </div>

      <div className="relative z-10 flex flex-col items-center min-h-screen p-4 sm:p-8">

        {/* Header */}
        <header className="w-full max-w-4xl flex justify-between items-center mb-12">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/20">
              <span className="text-xl font-bold text-white">W</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-blue-500 to-purple-600">
              WebReader
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setIsDark(!isDark)} className={`p-2.5 rounded-full transition-all duration-300 ${isDark ? 'bg-gray-800 hover:bg-gray-700 text-yellow-400' : 'bg-white hover:bg-gray-100 text-gray-600 shadow-sm'}`}>
              {isDark ? <Sun size={20} /> : <Moon size={20} />}
            </button>
            <button onClick={() => setShowSettings(true)} className={`p-2.5 rounded-full transition-all duration-300 ${isDark ? 'bg-gray-800 hover:bg-gray-700 text-gray-300' : 'bg-white hover:bg-gray-100 text-gray-600 shadow-sm'}`}>
              <Settings size={20} />
            </button>
          </div>
        </header>

        {/* Main Content Area */}
        <main className="w-full max-w-4xl flex-1 flex flex-col items-center justify-center gap-8">

          {/* Reader Card */}
          <div
            className={`relative w-full rounded-3xl overflow-hidden transition-all duration-500 ${isDark
                ? 'bg-gray-900/60 border border-gray-800 backdrop-blur-xl shadow-2xl shadow-black/50'
                : 'bg-white/80 border border-gray-100 backdrop-blur-xl shadow-2xl shadow-blue-100/50'
              }`}
            style={{ maxWidth: appearance.containerWidth + 'px' }}
          >

            {/* Display Area */}
            <div
              className="min-h-[400px] flex flex-col items-center justify-center p-8 cursor-pointer relative group"
              onClick={() => words.length > 0 && setIsPlaying(!isPlaying)}
            >
              {loading ? (
                <div className="flex flex-col items-center gap-6">
                  <div className="relative">
                    <div className="w-16 h-16 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin"></div>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="w-8 h-8 bg-blue-500 rounded-full animate-pulse opacity-20"></div>
                    </div>
                  </div>
                  <div className="text-lg font-medium text-blue-500 animate-pulse">{statusMessage || "Processing..."}</div>
                </div>
              ) : words.length === 0 ? (
                <div className="text-center space-y-6">
                  <div className={`w-24 h-24 mx-auto rounded-3xl flex items-center justify-center ${isDark ? 'bg-gray-800' : 'bg-blue-50'}`}>
                    <BookOpen size={48} className={isDark ? 'text-gray-600' : 'text-blue-500'} />
                  </div>
                  <div>
                    <h2 className={`text-2xl font-bold mb-2 ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>Ready to Read?</h2>
                    <p className={`text-lg ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Upload a PDF or EPUB to get started</p>
                  </div>

                  <label className="inline-flex group relative">
                    <div className={`absolute -inset-0.5 bg-gradient-to-r from-blue-500 to-purple-600 rounded-full blur opacity-75 group-hover:opacity-100 transition duration-200`}></div>
                    <input type="file" onChange={handleUpload} accept=".pdf,.epub,.txt,.docx" className="hidden" />
                    <span className={`relative px-8 py-4 rounded-full font-bold text-lg cursor-pointer flex items-center gap-3 transition-transform active:scale-95 ${isDark ? 'bg-gray-900 text-white' : 'bg-white text-gray-900'}`}>
                      <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-500 to-purple-600 group-hover:text-blue-500 transition-colors">Select Document</span>
                    </span>
                  </label>

                  {manualBoxes === null && (
                    <p className="text-xs text-gray-500 mt-4">(Supports PDF, EPUB, TXT, DOCX)</p>
                  )}
                </div>
              ) : (
                <RSVPDisplay words={words} images={images} index={index} settings={settings} appearance={appearance} isDark={isDark} />
              )}
            </div>

            {/* Control Bar */}
            {words.length > 0 && (
              <div className={`px-8 py-6 border-t ${isDark ? 'bg-gray-900/80 border-gray-800' : 'bg-gray-50/80 border-gray-100'}`}>

                {/* Progress Bar */}
                <div className="mb-6 relative group">
                  <div className={`h-2 w-full rounded-full overflow-hidden ${isDark ? 'bg-gray-800' : 'bg-gray-200'}`}>
                    <div
                      className="h-full bg-gradient-to-r from-blue-500 to-purple-600 transition-all duration-100 ease-out"
                      style={{ width: `${(index / words.length) * 100}%` }}
                    ></div>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max={words.length}
                    value={index}
                    onChange={(e) => setIndex(Number(e.target.value))}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  />
                  <div className="flex justify-between mt-2 text-xs font-medium font-mono opacity-50">
                    <span>{Math.floor((index / words.length) * 100)}%</span>
                    <span>{index} / {words.length}</span>
                  </div>
                </div>

                {/* Main Controls */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <button onClick={() => setShowChapterSelector(true)} className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-800 text-gray-400' : 'hover:bg-gray-200 text-gray-500'}`} title="Chapters">
                      <BookOpen size={20} />
                    </button>
                    {images.length > 0 && (
                      <button onClick={() => setShowAudioModal(true)} className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-800 text-gray-400' : 'hover:bg-gray-200 text-gray-500'}`} title="Gallery">
                        <Image size={20} />
                      </button>
                    )}
                  </div>

                  <div className="flex items-center gap-6">
                    <button onClick={() => setIndex(Math.max(0, index - 50))} className={`p-3 rounded-full transition-colors ${isDark ? 'hover:bg-gray-800 text-gray-300' : 'hover:bg-gray-200 text-gray-600'}`}>
                      <ChevronLeft size={24} />
                    </button>

                    <button
                      onClick={() => setIsPlaying(!isPlaying)}
                      className="relative group "
                    >
                      <div className={`absolute -inset-1 bg-gradient-to-r from-blue-500 to-purple-600 rounded-full blur opacity-75 group-hover:opacity-100 transition duration-200`}></div>
                      <div className={`relative px-8 py-3 rounded-full flex items-center gap-2 font-bold shadow-xl transition-transform active:scale-95 ${isDark ? 'bg-gray-900 text-white' : 'bg-white text-gray-900'}`}>
                        {isPlaying ? <Pause size={24} fill="currentColor" /> : <Play size={24} fill="currentColor" className="ml-1" />}
                        <span>{isPlaying ? "PAUSE" : "READ"}</span>
                      </div>
                    </button>

                    <button onClick={() => setIndex(Math.min(words.length, index + 50))} className={`p-3 rounded-full transition-colors ${isDark ? 'hover:bg-gray-800 text-gray-300' : 'hover:bg-gray-200 text-gray-600'}`}>
                      <ChevronRight size={24} />
                    </button>
                  </div>

                  <div className="flex items-center gap-2">
                    <button onClick={() => setIndex(0)} className={`p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-gray-800 text-gray-400' : 'hover:bg-gray-200 text-gray-500'}`} title="Restart">
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
        settings={settings}
        setSettings={setSettings}
        appearance={appearance}
        setAppearance={setAppearance}
        punctuationRules={punctuationRules}
        setPunctuationRules={setPunctuationRules}
        onClose={() => setShowSettings(false)}
        isDark={isDark}
      />}

      {showChapterSelector && <ChapterSelector
        chapters={chapters}
        onSelect={(idx) => { setIndex(idx); setShowChapterSelector(false); }}
        onClose={() => setShowChapterSelector(false)}
        isDark={isDark}
      />}

      {showAudioModal && <ImageGallery
        images={images}
        onClose={() => setShowAudioModal(false)}
        isDark={isDark}
      />}

    </div>
  );
}

export default App;
