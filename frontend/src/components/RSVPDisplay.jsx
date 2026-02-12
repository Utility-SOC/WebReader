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
            className={`relative w-full border-y-2 py-12 transition-colors duration-300 flex items-center justify-center overflow-hidden ${isDark ? 'border-gray-800 bg-gray-950/50 text-gray-100' : 'border-gray-100 bg-white/50 text-gray-900'}`}
            style={{
                fontFamily: appearance.fontFamily,
                fontSize: `${appearance.fontSize}px`,
                height: '400px'
            }}
        >
            {settings.guideLines && (
                <>
                    <div className={`absolute left-0 right-0 top-[35%] h-px w-full opacity-20 ${isDark ? 'bg-white' : 'bg-black'}`}></div>
                    <div className={`absolute left-0 right-0 bottom-[35%] h-px w-full opacity-20 ${isDark ? 'bg-white' : 'bg-black'}`}></div>
                </>
            )}
            <div className="flex items-baseline w-full justify-center text-center relative z-10 px-4">
                <div className="flex-1 text-right opacity-60 font-medium whitespace-pre">{settings.bionicBolding ? applyBionic(processed.left) : processed.left}</div>
                <div className={`mx-1 font-bold transform transition-transform duration-75 ${processed.isPivot ? 'text-blue-500 scale-110' : ''}`}>{processed.center}</div>
                <div className="flex-1 text-left opacity-60 font-medium whitespace-pre">{settings.bionicBolding ? applyBionic(processed.right) : processed.right}</div>
            </div>
        </div>
    );
};

export default RSVPDisplay;
