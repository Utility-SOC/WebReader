import React, { useState } from 'react';
import { Image, X } from 'lucide-react';

const ImageGallery = ({ images, isDark }) => {
    if (!images || images.length === 0) return null;
    const [isOpen, setIsOpen] = useState(false);
    if (!isOpen) return (
        <button onClick={() => setIsOpen(true)} className="fixed bottom-4 right-4 bg-orange-600 hover:bg-orange-500 text-white p-3 rounded-full shadow-lg z-50 flex items-center gap-2">
            <Image size={24} /> <span className="font-bold">{images.length} Images</span>
        </button>
    );
    return (
        <div className="fixed inset-y-0 right-0 w-80 bg-gray-900 shadow-2xl z-50 border-l border-gray-700 flex flex-col transform transition-transform">
            <div className="p-4 bg-gray-800 border-b border-gray-700 flex justify-between items-center text-white">
                <h3 className="font-bold">Extracted Images</h3>
                <button onClick={() => setIsOpen(false)} className="hover:text-red-400"><X size={20} /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {images.map((img, i) => (
                    <div key={i} className="bg-gray-800 rounded p-2 border border-gray-700">
                        <img src={img.src} alt={img.name} className="w-full h-auto rounded" />
                        <div className="text-xs text-gray-400 mt-2 truncate">{img.name}</div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default ImageGallery;
