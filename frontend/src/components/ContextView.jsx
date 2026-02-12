import React from 'react';

const ContextView = ({ words, index, isDark, appearance }) => {
    if (!words || words.length === 0) return null;

    const start = Math.max(0, index - 20);
    const end = Math.min(words.length, index + 30);
    const before = words.slice(start, index).join(" ");
    const current = words[index];
    const after = words.slice(index + 1, end).join(" ");

    return (
        <div className={`p-4 rounded-lg mt-4 text-center leading-relaxed h-32 overflow-y-auto custom-scrollbar ${isDark ? 'bg-gray-800 text-gray-300' : 'bg-gray-100 text-gray-700'}`}
            style={{ fontFamily: appearance.fontFamily, fontSize: '18px' }}
        >
            <span className="opacity-60">{before}</span>
            <span className={`mx-1 font-bold ${isDark ? 'text-white bg-blue-900/50 px-1 rounded' : 'text-black bg-yellow-200 px-1 rounded'}`}>
                {current}
            </span>
            <span className="opacity-60">{after}...</span>
        </div>
    );
};

export default ContextView;
