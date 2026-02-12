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
      initialBoxes={manualBoxes}
      onCancel={() => setShowEditor(false)}
      onFinish={handleManualFinish}
    />;
  }

  return (
    <div className={`min-h-screen flex flex-col ${isDark ? 'bg-gray-800' : 'bg-gray-50'}`}>
      <header className={`p-4 shadow-md ${isDark ? 'bg-gray-900 text-white' : 'bg-white text-gray-800'} flex justify-between items-center`}>
        <h1 className="text-xl font-bold flex items-center gap-2"><span className="text-blue-500">⚡</span> SpeedReader Web</h1>
        <div className="flex gap-2">
          <button onClick={() => setShowAudioModal(true)} className="p-2 rounded hover:bg-gray-700 text-xl" title="Audio Options" disabled={!words.length}><Volume2 size={24} /></button>
          <button onClick={() => setShowSettings(true)} className="p-2 rounded hover:bg-gray-700 text-xl" title="Settings"><Settings size={24} /></button>
          <button onClick={() => setIsDark(!isDark)} className="p-2 rounded hover:bg-gray-700">{isDark ? <Sun size={24} /> : <Moon size={24} />}</button>
        </div>
      </header>

      {showChapterSelector && (
        <ChapterSelector
          chapters={chapters}
          onSelect={(startIndex) => {
            setIndex(startIndex);
            setShowChapterSelector(false);
          }}
          onCancel={() => setShowChapterSelector(false)}
        />
      )}

      {showAudioModal && (
        <AudioModal
          filename={tempFile ? tempFile.filename : (words.length > 0 ? "document.pdf" : "")}
          pageCount={tempFile ? tempFile.page_count : (chapters.length > 0 ? chapters.length : 999)}
          manualBoxes={manualBoxes}
          onCancel={() => setShowAudioModal(false)}
        />
      )}

      <main className="flex-1 flex flex-col w-full p-4 gap-6 items-center">
        <div className="w-full max-w-lg mb-4">
          <input type="file" onChange={handleUpload} className="block w-full text-sm text-gray-500
                    file:mr-4 file:py-2 file:px-4
                    file:rounded-full file:border-0
                    file:text-sm file:font-semibold
                    file:bg-blue-50 file:text-blue-700
                    hover:file:bg-blue-100" />
        </div>

        <div className={`rounded-xl shadow-lg overflow-hidden ${isDark ? 'bg-gray-900' : 'bg-white'} min-h-[400px] flex flex-col relative w-full transition-all duration-300`}
          style={{ maxWidth: appearance.containerWidth + 'px' }}>

          <div className="flex-1 flex flex-col justify-center items-center relative min-h-[250px] p-4" onClick={() => setIsPlaying(!isPlaying)}>
            {loading ? (
              <div className="flex flex-col items-center gap-4">
                <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div>
                <div className="animate-pulse text-blue-600 font-bold text-lg">{statusMessage || "Processing..."}</div>
              </div>
            ) : (
              <RSVPDisplay words={words} images={images} index={index} settings={settings} appearance={appearance} isDark={isDark} />
            )}
          </div>

          {/* Controls */}
          <div className={`p-4 ${isDark ? 'bg-gray-800' : 'bg-gray-100'} border-t ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
            <div className="flex items-center justify-center gap-4">
              <button onClick={() => setIndex(Math.max(0, index - 10))} className="p-2 rounded-full bg-gray-600 hover:bg-gray-500 text-white"><ChevronLeft /></button>
              <button onClick={() => setIsPlaying(!isPlaying)} className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3 rounded-full font-bold shadow-lg flex items-center gap-2">
                {isPlaying ? <Pause /> : <Play />} {isPlaying ? "PAUSE" : "PLAY"}
              </button>
              <button onClick={() => setIndex(Math.min(words.length, index + 10))} className="p-2 rounded-full bg-gray-600 hover:bg-gray-500 text-white"><ChevronRight /></button>
            </div>
            <div className="text-center mt-2 text-xs opacity-50 font-mono text-gray-500">{index} / {words.length}</div>
            <input type="range" min="0" max={words.length} value={index} onChange={(e) => setIndex(Number(e.target.value))} className="w-full mt-2" />
          </div>
        </div>

        <ContextView words={words} index={index} isDark={isDark} appearance={appearance} />

        <ImageGallery images={images} isDark={isDark} />

        {/* Settings Modal */}
        <SettingsModal
          isOpen={showSettings}
          onClose={() => setShowSettings(false)}
          settings={settings}
          setSettings={setSettings}
          appearance={appearance}
          setAppearance={setAppearance}
          punctuationRules={punctuationRules}
          setPunctuationRules={setPunctuationRules}
          isDark={isDark}
        />
      </main >
    </div >
  )
}

export default App;
