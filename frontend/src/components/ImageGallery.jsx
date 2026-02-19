import React, { useState } from 'react';
import { Image, X, Download, Maximize2 } from 'lucide-react';

const ImageGallery = ({ images, isDark, onClose }) => {
    // If used as a modal (passed via props in App.jsx usually), we control it there.
    // But this component seems to have dual usage or was refactored. 
    // Based on App.jsx: <ImageGallery images={images} onClose={() => setShowAudioModal(false)} ... />
    // It seems 'showAudioModal' was misused for naming, but let's stick to the App.jsx usage.

    if (!images || images.length === 0) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={onClose}></div>

            <div className={`relative w-full max-w-5xl h-[80vh] rounded-3xl shadow-2xl flex flex-col overflow-hidden transform transition-all scale-100 ${isDark ? 'bg-gray-900/90 border border-gray-700 text-white' : 'bg-white/90 border border-gray-200 text-gray-900'
                }`}>

                {/* Header */}
                <div className={`flex items-center justify-between px-6 py-4 border-b ${isDark ? 'border-gray-700' : 'border-gray-200'}`}>
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-indigo-500/10 rounded-lg text-indigo-500">
                            <Image size={24} />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold tracking-tight">Extracted Images</h2>
                            <p className={`text-sm ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{images.length} images found</p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className={`p-2 rounded-full transition-colors ${isDark ? 'hover:bg-gray-800 text-gray-400 hover:text-white' : 'hover:bg-gray-100 text-gray-500 hover:text-gray-900'}`}
                    >
                        <X size={24} />
                    </button>
                </div>

                {/* Grid */}
                <div className="flex-1 overflow-y-auto p-6">
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                        {images.map((img, i) => (
                            <div key={i} className={`group relative rounded-2xl overflow-hidden border transition-all duration-300 hover:shadow-xl ${isDark ? 'bg-gray-800 border-gray-700 hover:border-indigo-500/50' : 'bg-white border-gray-200 hover:border-indigo-400'
                                }`}>
                                <div className="aspect-video w-full overflow-hidden bg-gray-100/5 relative">
                                    <img
                                        src={img.src}
                                        alt={img.name}
                                        className="w-full h-full object-contain transition-transform duration-500 group-hover:scale-105"
                                    />
                                    {/* Overlay */}
                                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                                        <a
                                            href={img.src}
                                            download={img.name + ".png"}
                                            className="p-2 bg-white/10 hover:bg-white/20 hover:scale-110 rounded-full backdrop-blur-md text-white transition-all transform"
                                            title="Download"
                                        >
                                            <Download size={20} />
                                        </a>
                                        <button
                                            className="p-2 bg-white/10 hover:bg-white/20 hover:scale-110 rounded-full backdrop-blur-md text-white transition-all transform"
                                            title="View Full"
                                            onClick={() => window.open(img.src, '_blank')}
                                        >
                                            <Maximize2 size={20} />
                                        </button>
                                    </div>
                                </div>
                                <div className={`p-4 ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
                                    <h4 className="font-medium truncate text-sm" title={img.name}>{img.name}</h4>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ImageGallery;
