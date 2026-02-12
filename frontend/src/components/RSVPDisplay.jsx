import React from 'react';

const RSVPDisplay = ({ words, index, settings, appearance, isDark, images }) => {
    if (!words || words.length === 0) return <div className="text-center p-10 opacity-50">Upload a file to begin</div>;

    const currentItem = words[index];
    const isFigure = currentItem && currentItem.startsWith("[FIGURE:");

    if (isFigure) {
        const name = currentItem.replace("[FIGURE:", "").replace("]", "").trim();
        const imgData = images.find(img => img.name === name);

        return (
            <div className="flex flex-col items-center justify-center p-4">
                {imgData ? (
                    <img src={imgData.src} className="max-h-[500px] border shadow-lg rounded object-contain" alt={name} />
                ) : (
                    <div className="p-10 border border-dashed rounded bg-gray-100">Image {name}</div>
                )}
                <div className="mt-2 text-sm text-gray-500 font-mono">{name}</div>
            </div>
        );
    }

    const currentWords = words.slice(index, index + settings.chunkSize);

    // Process Chunk Logic
    const text = currentWords.join(" ");
    let processed;
    if (!settings.orpCentering) {
        processed = { left: "", center: text, right: "", isPivot: false };
    } else {
        const pivotIndex = Math.floor(text.length * settings.orpOffset);
        processed = {
            left: text.slice(0, pivotIndex),
            center: text[pivotIndex],
            right: text.slice(pivotIndex + 1),
            isPivot: true
        };
    }

    const applyBionic = (text) => {
        if (!text) return text;
        const split = Math.ceil(text.length / 2);
        return <span><b className="font-extrabold">{text.slice(0, split)}</b><span className="opacity-80">{text.slice(split)}</span></span>;
    };

    return (
        <div
            className={`relative w-full border-y-2 ${isDark ? 'border-gray-700 bg-gray-900 text-gray-100' : 'border-gray-200 bg-white text-gray-900'} transition-colors duration-300`}
            style={{
                fontFamily: appearance.fontFamily,
                fontSize: `${appearance.fontSize}px`
            }}
        >
            {settings.guideLines && (
                <>
                    <div className={`guide-line guide-top ${isDark ? 'dark' : ''}`}></div>
                    <div className={`guide-line guide-bottom ${isDark ? 'dark' : ''}`}></div>
                </>
            )}
            <div className="pivot-container" style={{ minHeight: appearance.fontSize * 2 + 'px' }}>
                <div className="pivot-left">{settings.bionicBolding ? applyBionic(processed.left) : processed.left}</div>
                <div className={`pivot-center ${processed.isPivot ? 'text-red-500' : ''}`}>{processed.center}</div>
                <div className="pivot-right">{settings.bionicBolding ? applyBionic(processed.right) : processed.right}</div>
            </div>
        </div>
    );
};

export default RSVPDisplay;
