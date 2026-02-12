import React, { useState, useEffect, useRef } from 'react';
import { ArrowLeft, ArrowRight, Trash2, Check, X, Crop, Image as ImageIcon, Type } from 'lucide-react';

const PdfManualEditor = ({ filename, pageCount, initialBoxes, onCancel, onFinish }) => {
    const [pageIdx, setPageIdx] = useState(0);
    const [tool, setTool] = useState('text'); // 'text' | 'image'
    const [imageUrl, setImageUrl] = useState(null);

    const [boxesMap, setBoxesMap] = useState(initialBoxes || {});
    const [selectedBoxIdx, setSelectedBoxIdx] = useState(null);

    // New State
    const [startPage, setStartPage] = useState(1);
    const [fitWidth, setFitWidth] = useState(true);

    // Interaction State
    const [interaction, setInteraction] = useState({
        mode: 'idle', // 'idle', 'drawing', 'moving', 'resizing'
        startPoint: { x: 0, y: 0 },
        initialBox: null,
        handle: null
    });

    // Drawing State (Draft box)
    const [draftBox, setDraftBox] = useState(null);

    const imgRef = useRef(null);

    // Load Image
    useEffect(() => {
        const loadPage = async () => {
            // Using proxy path from vite config
            const url = `/pdf/${filename}/page/${pageIdx + 1}`;
            setImageUrl(url);
            setSelectedBoxIdx(null);
        };
        loadPage();
    }, [filename, pageIdx]);

    // Keyboard Listeners (Delete + Nudge)
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (selectedBoxIdx === null) return;

            // Delete
            if (e.key === 'Delete' || e.key === 'Backspace') {
                deleteSelectedBox();
                return;
            }

            // Nudge / Resize
            if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
                e.preventDefault();
                const step = 1; // Precision 1px
                const dx = (e.key === 'ArrowRight' ? step : (e.key === 'ArrowLeft' ? -step : 0));
                const dy = (e.key === 'ArrowDown' ? step : (e.key === 'ArrowUp' ? -step : 0));

                setBoxesMap(prev => {
                    const pageKey = String(pageIdx);
                    const list = [...(prev[pageKey] || [])];
                    if (!list[selectedBoxIdx]) return prev;

                    const box = { ...list[selectedBoxIdx] };

                    if (e.shiftKey) {
                        // RESIZE (Expand/Contract dimensions)
                        box.w = Math.max(5, box.w + dx);
                        box.h = Math.max(5, box.h + dy);
                    } else {
                        // MOVE
                        box.x += dx;
                        box.y += dy;
                    }
                    list[selectedBoxIdx] = box;
                    return { ...prev, [pageKey]: list };
                });
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedBoxIdx, pageIdx, boxesMap]);

    // ---------------------------
    // MOUSE HANDLERS
    // ---------------------------
    const getLoc = (e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        let scale = 1;
        if (fitWidth && imgRef.current) {
            scale = imgRef.current.naturalWidth / rect.width;
        }

        return {
            x: (e.clientX - rect.left) * scale,
            y: (e.clientY - rect.top) * scale
        };
    };

    const handleMouseDown = (e) => {
        const { x, y } = getLoc(e);

        // 1. Check for Resize Handle Hit (if selection active)
        if (selectedBoxIdx !== null && boxesMap[String(pageIdx)]) {
            const handle = getHandleAt(x, y, boxesMap[String(pageIdx)][selectedBoxIdx]);
            if (handle) {
                setInteraction({
                    mode: 'resizing',
                    startPoint: { x, y },
                    initialBox: { ...boxesMap[String(pageIdx)][selectedBoxIdx] },
                    handle
                });
                e.stopPropagation();
                return;
            }
        }

        // 2. Check for Box Hit (Move or Select)
        const hitIdx = getBoxAt(x, y);
        if (hitIdx !== null) {
            setSelectedBoxIdx(hitIdx);
            setInteraction({
                mode: 'moving',
                startPoint: { x, y },
                initialBox: { ...boxesMap[String(pageIdx)][hitIdx] },
                handle: null
            });
            e.stopPropagation();
            return;
        }

        // 3. Background -> Start Drawing
        setSelectedBoxIdx(null);
        setInteraction({ mode: 'drawing', startPoint: { x, y }, initialBox: null, handle: null });
        setDraftBox({ x, y, w: 0, h: 0, type: tool });
    };

    const handleMouseMove = (e) => {
        const { x, y } = getLoc(e);

        if (interaction.mode === 'drawing') {
            const start = interaction.startPoint;
            setDraftBox({
                x: Math.min(start.x, x),
                y: Math.min(start.y, y),
                w: Math.abs(x - start.x),
                h: Math.abs(y - start.y),
                type: tool
            });
        } else if (interaction.mode === 'moving') {
            const dx = x - interaction.startPoint.x;
            const dy = y - interaction.startPoint.y;

            updateBox(selectedBoxIdx, {
                x: interaction.initialBox.x + dx,
                y: interaction.initialBox.y + dy
            });
        } else if (interaction.mode === 'resizing') {
            const dx = x - interaction.startPoint.x;
            const dy = y - interaction.startPoint.y;
            const init = interaction.initialBox;
            let newBox = { ...init };

            // Handle Logic
            if (interaction.handle.includes('e')) newBox.w = Math.max(5, init.w + dx);
            if (interaction.handle.includes('s')) newBox.h = Math.max(5, init.h + dy);
            if (interaction.handle.includes('w')) {
                newBox.x = init.x + dx;
                newBox.w = Math.max(5, init.w - dx);
            }
            if (interaction.handle.includes('n')) {
                newBox.y = init.y + dy;
                newBox.h = Math.max(5, init.h - dy);
            }

            updateBox(selectedBoxIdx, newBox);
        }
    };

    const handleMouseUp = () => {
        if (interaction.mode === 'drawing' && draftBox) {
            if (draftBox.w > 5 && draftBox.h > 5) {
                addBox(draftBox);
                setSelectedBoxIdx((boxesMap[String(pageIdx)] || []).length);
            }
            setDraftBox(null);
        }
        setInteraction({ mode: 'idle', startPoint: { x: 0, y: 0 }, initialBox: null, handle: null });
    };

    // Helpers
    const getBoxAt = (x, y) => {
        const boxes = boxesMap[String(pageIdx)] || [];
        // Check in reverse order (top first)
        for (let i = boxes.length - 1; i >= 0; i--) {
            const b = boxes[i];
            if (x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h) return i;
        }
        return null;
    };

    const getHandleAt = (mx, my, box) => {
        const HANDLE_SIZE = 20; // Larger for touch
        const hit = (hx, hy) => Math.abs(mx - hx) <= HANDLE_SIZE && Math.abs(my - hy) <= HANDLE_SIZE;

        if (hit(box.x, box.y)) return 'nw';
        if (hit(box.x + box.w, box.y)) return 'ne';
        if (hit(box.x, box.y + box.h)) return 'sw';
        if (hit(box.x + box.w, box.y + box.h)) return 'se';
        return null;
    };

    const addBox = (box) => {
        setBoxesMap(prev => {
            const k = String(pageIdx);
            return { ...prev, [k]: [...(prev[k] || []), box] };
        });
    };

    const updateBox = (idx, newAttrs) => {
        setBoxesMap(prev => {
            const k = String(pageIdx);
            const list = [...(prev[k] || [])];
            list[idx] = { ...list[idx], ...newAttrs };
            return { ...prev, [k]: list };
        });
    };

    const deleteSelectedBox = () => {
        if (selectedBoxIdx === null) return;
        setBoxesMap(prev => {
            const k = String(pageIdx);
            const list = prev[k].filter((_, i) => i !== selectedBoxIdx);
            return { ...prev, [k]: list };
        });
        setSelectedBoxIdx(null);
    };

    const setAsStart = () => {
        setStartPage(pageIdx + 1);
        alert(`Starting Reading from Page ${pageIdx + 1}`);
    };

    const prevPage = () => setPageIdx(Math.max(0, pageIdx - 1));
    const nextPage = () => {
        if (pageIdx >= pageCount - 1) return;
        const nextIdx = pageIdx + 1;
        // Auto Copy
        const currentBoxes = boxesMap[String(pageIdx)] || [];
        const nextBoxes = boxesMap[String(nextIdx)];
        if (currentBoxes.length > 0 && (!nextBoxes || nextBoxes.length === 0)) {
            setBoxesMap(prev => ({ ...prev, [String(nextIdx)]: [...currentBoxes] }));
        }
        setPageIdx(nextIdx);
    };

    return (
        <div className="fixed inset-0 bg-gray-900 bg-opacity-95 z-50 flex flex-col text-white select-none">
            {/* Toolbar */}
            <div className="p-3 bg-gray-800 flex flex-wrap gap-2 justify-between items-center shadow-md border-b border-gray-700">
                <div className="flex items-center gap-2">
                    <h2 className="font-bold text-lg text-blue-400 hidden sm:block">Editor</h2>
                    <div className="flex bg-gray-700 rounded p-0.5">
                        <button onClick={prevPage} disabled={pageIdx === 0} className="px-3 py-1 hover:bg-gray-600 rounded-l disabled:opacity-50 border-r border-gray-600">
                            <ArrowLeft size={16} />
                        </button>
                        <span className="px-3 py-1 font-mono text-sm flex items-center bg-gray-600">Page {pageIdx + 1} / {pageCount}</span>
                        <button onClick={nextPage} disabled={pageIdx === pageCount - 1} className="px-3 py-1 hover:bg-gray-600 rounded-r disabled:opacity-50">
                            <ArrowRight size={16} />
                        </button>
                    </div>
                </div>

                <div className="flex gap-2 items-center overflow-x-auto">
                    <button onClick={() => setTool('text')} title="Text Query" className={`p-2 rounded ${tool === 'text' ? 'bg-blue-600 ring-1 ring-white' : 'bg-gray-700'}`}>
                        <Type size={20} />
                    </button>
                    <button onClick={() => setTool('image')} title="Image Extraction" className={`p-2 rounded ${tool === 'image' ? 'bg-orange-600 ring-1 ring-white' : 'bg-gray-700'}`}>
                        <ImageIcon size={20} />
                    </button>
                    <button onClick={() => setFitWidth(!fitWidth)} className={`p-2 rounded bg-gray-700 text-xs font-bold w-12`}>{fitWidth ? 'FIT' : '1:1'}</button>

                    {selectedBoxIdx !== null ? (
                        <button onClick={deleteSelectedBox} className="p-2 bg-red-600 rounded">
                            <Trash2 size={20} />
                        </button>
                    ) : (
                        <button onClick={setAsStart} className="px-2 py-1 bg-purple-600 rounded text-xs font-bold whitespace-nowrap" title="Start from this page">Start Here (pg{startPage})</button>
                    )}
                </div>

                <div className="flex gap-2">
                    <button onClick={onCancel} className="px-3 py-1 text-gray-400 hover:text-white text-sm flex items-center gap-1">
                        <X size={16} /> Cancel
                    </button>
                    <button onClick={() => {
                        // Normalize Scale to Relative (0.0 - 1.0)
                        const nw = imgRef.current ? imgRef.current.naturalWidth : 800;
                        const nh = imgRef.current ? imgRef.current.naturalHeight : 1100;
                        const normMap = {};
                        Object.keys(boxesMap).forEach(k => {
                            normMap[k] = boxesMap[k].map(b => {
                                // If already relative, keep as is
                                if (b.relative) return b;
                                // If absolute (pixels), normalize
                                return {
                                    ...b,
                                    relative: true,
                                    x: b.x / nw,
                                    y: b.y / nh,
                                    w: b.w / nw,
                                    h: b.h / nh
                                };
                            });
                        });
                        onFinish(normMap, startPage);
                    }} className="px-3 py-1 bg-green-600 hover:bg-green-500 rounded font-bold shadow-lg flex items-center gap-1">
                        <Check size={16} /> DONE
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-auto bg-gray-500 flex justify-center p-2 sm:p-4 cursor-default">
                <div className="relative shadow-2xl bg-white select-none box-default outline-none"
                    style={{
                        alignSelf: 'flex-start',
                        width: fitWidth ? '100%' : 'auto',
                        maxWidth: fitWidth ? '100%' : 'unset'
                    }}
                >
                    {imageUrl && (
                        <img
                            ref={imgRef}
                            src={imageUrl}
                            draggable="false"
                            className="block"
                            onLoad={(e) => {
                                const nw = e.target.naturalWidth;
                                const nh = e.target.naturalHeight;
                                const currentBoxes = boxesMap[String(pageIdx)];

                                if (currentBoxes && currentBoxes.some(b => b.relative)) {
                                    setBoxesMap(prev => {
                                        const list = prev[String(pageIdx)].map(b => {
                                            if (!b.relative) return b;
                                            return {
                                                ...b,
                                                relative: false,
                                                x: b.x * nw,
                                                y: b.y * nh,
                                                w: b.w * nw,
                                                h: b.h * nh
                                            };
                                        });
                                        return { ...prev, [String(pageIdx)]: list };
                                    });
                                }
                            }}
                            style={{
                                width: fitWidth ? '100%' : 'auto',
                                maxWidth: 'unset',
                                pointerEvents: 'none',
                                userSelect: 'none'
                            }}
                        />
                    )}
                    {/* Overlay */}
                    <div className="absolute inset-0 z-10"
                        onMouseDown={handleMouseDown}
                        onMouseMove={handleMouseMove}
                        onMouseUp={handleMouseUp}
                        onMouseLeave={handleMouseUp}
                        onClick={(e) => e.stopPropagation()}
                    >
                        {(boxesMap[String(pageIdx)] || []).map((box, i) => {
                            const isSelected = selectedBoxIdx === i;
                            const naturalW = imgRef.current?.naturalWidth || 800;
                            const scale = fitWidth && imgRef.current ? (imgRef.current.clientWidth / naturalW) : 1;

                            return (
                                <div key={i}
                                    className={`absolute border-2 flex items-center justify-center group ${box.type === 'image' ? 'border-orange-500 bg-orange-500/20' : 'border-blue-600 bg-blue-600/10'}`}
                                    style={{
                                        left: box.x * scale,
                                        top: box.y * scale,
                                        width: box.w * scale,
                                        height: box.h * scale,
                                        borderColor: isSelected ? (box.type == 'image' ? 'orange' : 'blue') : undefined,
                                        zIndex: isSelected ? 20 : 10,
                                        cursor: 'move'
                                    }}>
                                    <div className={`absolute -top-5 left-0 text-xs px-1.5 py-0.5 font-bold rounded text-white ${box.type === 'image' ? 'bg-orange-500' : 'bg-blue-600'} ${isSelected ? 'ring-1 ring-white' : ''}`}>{i + 1}</div>
                                    {isSelected && (<><div className="absolute -top-1.5 -left-1.5 w-3 h-3 bg-white border border-gray-500 cursor-nw-resize hover:bg-blue-200"></div><div className="absolute -top-1.5 -right-1.5 w-3 h-3 bg-white border border-gray-500 cursor-ne-resize hover:bg-blue-200"></div><div className="absolute -bottom-1.5 -left-1.5 w-3 h-3 bg-white border border-gray-500 cursor-sw-resize hover:bg-blue-200"></div><div className="absolute -bottom-1.5 -right-1.5 w-3 h-3 bg-white border border-gray-500 cursor-se-resize hover:bg-blue-200"></div></>)}
                                </div>
                            );
                        })}
                        {draftBox && (
                            <div className={`absolute border-2 border-dashed ${draftBox.type === 'image' ? 'border-orange-500 bg-orange-500/10' : 'border-blue-500 bg-blue-500/10'}`}
                                style={{
                                    left: draftBox.x * (fitWidth && imgRef.current ? (imgRef.current.clientWidth / imgRef.current.naturalWidth) : 1),
                                    top: draftBox.y * (fitWidth && imgRef.current ? (imgRef.current.clientWidth / imgRef.current.naturalWidth) : 1),
                                    width: draftBox.w * (fitWidth && imgRef.current ? (imgRef.current.clientWidth / imgRef.current.naturalWidth) : 1),
                                    height: draftBox.h * (fitWidth && imgRef.current ? (imgRef.current.clientWidth / imgRef.current.naturalWidth) : 1),
                                    pointerEvents: 'none'
                                }}
                            />
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default PdfManualEditor;
