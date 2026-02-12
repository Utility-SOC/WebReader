import React, { useState } from 'react';
import { X } from 'lucide-react';
import { FONTS, PRESETS } from '../constants';

const SettingsModal = ({
    isOpen,
    onClose,
    settings,
    setSettings,
    appearance,
    setAppearance,
    punctuationRules,
    setPunctuationRules,
    isDark
}) => {
    if (!isOpen) return null;

    const [newRuleStr, setNewRuleStr] = useState("");
    const [newRuleVal, setNewRuleVal] = useState(1.5);

    const handleAddRule = () => {
        if (!newRuleStr) return;
        setPunctuationRules(prev => [...prev, { str: newRuleStr, val: Number(newRuleVal) }]);
        setNewRuleStr("");
        setNewRuleVal(1.5);
    };

    const handleDeleteRule = (idx) => {
        setPunctuationRules(prev => prev.filter((_, i) => i !== idx));
    };

    return (
        <div className="fixed inset-0 bg-gray-900 bg-opacity-95 z-50 flex items-center justify-center p-4">
            <div className={`rounded-xl shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col ${isDark ? 'bg-gray-800 text-white' : 'bg-white text-gray-900'}`}>
                <div className="p-4 border-b border-gray-700 flex justify-between items-center">
                    <h2 className="font-bold text-lg flex items-center gap-2">⚙️ Advanced Settings</h2>
                    <button onClick={onClose} className="text-gray-500 hover:text-red-500"><X size={20} /></button>
                </div>
                <div className="p-6 overflow-y-auto space-y-8">

                    {/* Equalizer */}
                    <div>
                        <h3 className="font-bold mb-4 border-b border-gray-600 pb-2 flex items-center gap-2"><span>⚖️</span> Punctuation Equalizer</h3>
                        <div className="text-xs opacity-70 mb-2">Adjust delay multipliers for specific text patterns.</div>
                        <div className="space-y-2 mb-4 max-h-40 overflow-y-auto bg-black/10 p-2 rounded border border-gray-500/30">
                            {punctuationRules.map((rule, i) => (
                                <div key={i} className="flex justify-between items-center text-sm p-1">
                                    <span className="font-mono bg-white/10 px-1 rounded">"{rule.str === "\\n\\n" ? "¶" : rule.str}"</span>
                                    <span className="font-bold text-blue-400">{rule.val}x</span>
                                    <button onClick={() => handleDeleteRule(i)} className="text-red-500 hover:text-red-700 font-bold px-2">×</button>
                                </div>
                            ))}
                        </div>
                        <div className="flex gap-2">
                            <input placeholder="String" value={newRuleStr} onChange={e => setNewRuleStr(e.target.value)} className="w-24 p-2 text-sm border rounded bg-transparent border-gray-600" />
                            <input type="number" step="0.1" value={newRuleVal} onChange={e => setNewRuleVal(e.target.value)} className="w-24 p-2 text-sm border rounded bg-transparent border-gray-600" />
                            <button onClick={handleAddRule} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm font-bold">ADD</button>
                        </div>
                    </div>

                    {/* Mechanics */}
                    <div>
                        <h3 className="font-bold mb-4 border-b border-gray-600 pb-2">🎯 Reading Mechanics</h3>
                        {/* ORP Pivot */}
                        <div className="mb-6">
                            <div className="flex justify-between text-sm mb-1"><label>ORP Pivot Position</label><span className="font-mono text-blue-400">{Math.round(settings.orpOffset * 100)}%</span></div>
                            <input type="range" min="0.1" max="0.9" step="0.05" value={settings.orpOffset} onChange={e => setSettings({ ...settings, orpOffset: Number(e.target.value) })} className="w-full" />
                        </div>

                        {/* Toggles */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <label className="flex items-center gap-2 cursor-pointer select-none p-3 rounded bg-black/10 hover:bg-black/20"><input type="checkbox" checked={settings.guideLines} onChange={e => setSettings({ ...settings, guideLines: e.target.checked })} /> <span>Show Guide Lines</span></label>
                            <label className="flex items-center gap-2 cursor-pointer select-none p-3 rounded bg-black/10 hover:bg-black/20"><input type="checkbox" checked={settings.bionicBolding} onChange={e => setSettings({ ...settings, bionicBolding: e.target.checked })} /> <span>Bionic Bolding</span></label>
                            <label className="flex items-center gap-2 cursor-pointer select-none p-3 rounded bg-black/10 hover:bg-black/20"><input type="checkbox" checked={settings.orpCentering} onChange={e => setSettings({ ...settings, orpCentering: e.target.checked })} /> <span>Force ORP Centering</span></label>
                        </div>
                    </div>
                </div>
                <div className="p-4 border-t border-gray-700 bg-black/10 rounded-b-xl text-right">
                    <button onClick={onClose} className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded font-bold">Close</button>
                </div>
            </div>
        </div>
    );
};

export default SettingsModal;
