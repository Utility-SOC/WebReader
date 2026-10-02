import React from 'react';
import { X } from 'lucide-react';
import Modal from './Modal';

const ChapterSelector = ({ chapters, onSelect, onClose }) => {
    return (
        <Modal labelId="chapters-title" onClose={onClose} className="fixed inset-0 bg-gray-900 bg-opacity-95 z-50 flex items-center justify-center p-4">
            <div className="bg-white text-gray-900 rounded-lg shadow-2xl max-w-md w-full max-h-[80vh] flex flex-col">
                <div className="p-4 border-b flex justify-between items-center bg-gray-50 rounded-t-lg">
                    <h2 id="chapters-title" className="font-bold text-lg">Select Start Chapter</h2>
                    <button onClick={onClose} aria-label="Close chapter list" className="text-gray-600 hover:text-red-600"><X size={20} /></button>
                </div>
                <div className="flex-1 overflow-y-auto p-2">
                    {chapters.map((chap, i) => (
                        <button key={i} onClick={() => onSelect(chap.start_index)}
                            className="w-full text-left p-3 hover:bg-blue-50 border-b border-gray-100 last:border-0 flex justify-between items-center group transition-colors">
                            <span className="font-semibold text-gray-700 group-hover:text-blue-700">{chap.title}</span>
                            <span className="text-xs text-gray-600 bg-gray-100 px-2 py-1 rounded group-hover:bg-blue-100">{chap.word_count}w</span>
                        </button>
                    ))}
                </div>
                <div className="p-3 border-t bg-gray-50 text-right rounded-b-lg">
                    <button onClick={() => onSelect(0)} className="text-sm text-gray-700 hover:underline">Start from Beginning</button>
                </div>
            </div>
        </Modal>
    );
};

export default ChapterSelector;
