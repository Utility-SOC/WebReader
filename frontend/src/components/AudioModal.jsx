import React, { useState, useEffect } from 'react';
import { X, Mic, Download } from 'lucide-react';

const AudioModal = ({ filename, pageCount, manualBoxes, onCancel }) => {
    const [voices, setVoices] = useState([]);
    const [loadingVoices, setLoadingVoices] = useState(true);
    const [selectedVoice, setSelectedVoice] = useState("");
    const [startPage, setStartPage] = useState(1);
    const [endPage, setEndPage] = useState(pageCount || 1);
    const [isDownloading, setIsDownloading] = useState(false);

    useEffect(() => {
        const fetchVoices = async () => {
            try {
                const res = await fetch("/tts/voices");
                const data = await res.json();
                if (data.voices && data.voices.length > 0) {
                    setVoices(data.voices);
                    setSelectedVoice(data.voices[0].id);
                }
            } catch (err) {
                console.error("Failed to load voices", err);
            } finally {
                setLoadingVoices(false);
            }
        };
        fetchVoices();
    }, []);

    const handleDownload = async () => {
        if (!filename) return;
        setIsDownloading(true);
        try {
            const res = await fetch("/tts/download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    filename: filename,
                    start_page: Number(startPage),
                    end_page: Number(endPage),
                    voice_id: selectedVoice || undefined,
                    manual_boxes: manualBoxes || undefined
                })
            });

            if (!res.ok) {
                if (res.status === 404) {
                    throw new Error("Session Expired: The file is no longer on the server. Please upload it again.");
                }
                const errText = await res.text();
                try {
                    const json = JSON.parse(errText);
                    throw new Error(json.detail || errText);
                } catch (e) {
                    throw new Error(errText);
                }
            }

            // Create blob and force download
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.style.display = "none";
            a.href = url;
            // Try to get filename from header or fallback
            const header = res.headers.get('Content-Disposition');
            let dlName = `${filename.replace('.pdf', '')}_audio.wav`;
            if (header && header.indexOf('filename=') !== -1) {
                dlName = header.split('filename=')[1].replace(/['"]/g, '');
            }
            a.download = dlName;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);

            onCancel(); // Close on success
        } catch (err) {
            alert("Download Failed: " + err.message);
        } finally {
            setIsDownloading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-gray-900 bg-opacity-95 z-50 flex items-center justify-center p-4">
            <div className="bg-gray-800 text-white rounded-lg shadow-2xl max-w-md w-full border border-gray-700 font-sans">
                <div className="p-4 border-b border-gray-700 flex justify-between items-center">
                    <h2 className="font-bold text-lg flex items-center gap-2"><Mic size={20} /> Audio Options</h2>
                    <button onClick={onCancel} className="text-gray-400 hover:text-white"><X size={20} /></button>
                </div>
                <div className="p-6 space-y-4">
                    {/* Voice Selector */}
                    <div>
                        <label className="block text-sm font-bold mb-1 text-gray-400">Select Voice</label>
                        {loadingVoices ? (
                            <div className="text-sm opacity-50">Loading voices...</div>
                        ) : (
                            <select
                                value={selectedVoice}
                                onChange={(e) => setSelectedVoice(e.target.value)}
                                className="w-full p-2 rounded bg-gray-900 border border-gray-600 focus:border-blue-500 outline-none"
                            >
                                {voices.map(v => (
                                    <option key={v.id} value={v.id}>{v.name} ({v.lang})</option>
                                ))}
                            </select>
                        )}
                    </div>

                    {/* Page Range */}
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-bold mb-1 text-gray-400">Start Page</label>
                            <input
                                type="number"
                                min="1"
                                max={pageCount || 9999}
                                value={startPage}
                                onChange={(e) => setStartPage(e.target.value)}
                                className="w-full p-2 rounded bg-gray-900 border border-gray-600 focus:border-blue-500 outline-none"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-bold mb-1 text-gray-400">End Page</label>
                            <input
                                type="number"
                                min="1"
                                max={pageCount || 9999}
                                value={endPage}
                                onChange={(e) => setEndPage(e.target.value)}
                                className="w-full p-2 rounded bg-gray-900 border border-gray-600 focus:border-blue-500 outline-none"
                            />
                        </div>
                    </div>
                </div>
                <div className="p-4 border-t border-gray-700 flex justify-end gap-2 bg-gray-900/50 rounded-b-lg">
                    <button onClick={onCancel} className="px-4 py-2 text-gray-400 hover:text-white font-semibold">Cancel</button>
                    <button
                        onClick={handleDownload}
                        disabled={isDownloading || loadingVoices}
                        className={`px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded font-bold shadow-lg flex items-center gap-2 ${isDownloading ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        {isDownloading ? (
                            <><span>Processing...</span></>
                        ) : (
                            <><Download size={18} /> <span>Download MP3</span></>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default AudioModal;
