export const FONTS = [
    { name: "Courier New", label: "Monospace (Default)", family: "'Courier New', monospace" },
    { name: "Atkinson Hyperlegible", label: "Atkinson Hyperlegible (Low Vision)", family: "'Atkinson Hyperlegible', sans-serif" },
    { name: "OpenDyslexic", label: "OpenDyslexic (Dyslexia)", family: "'OpenDyslexic', sans-serif" },
    { name: "Lexend", label: "Lexend (Reading Speed)", family: "'Lexend', sans-serif" },
    { name: "Merriweather", label: "Merriweather (Serif)", family: "'Merriweather', serif" },
    { name: "Noto Sans", label: "Noto Sans (Clear)", family: "'Noto Sans', sans-serif" },
    { name: "Arial", label: "Arial (Standard)", family: "Arial, sans-serif" },
    { name: "Comic Sans MS", label: "Comic Sans (Casual)", family: "'Comic Sans MS', 'Comic Sans', cursive" }
];

export const PRESETS = {
    standard: {
        id: "standard",
        label: "Standard RSVP",
        citation: "Forster, K. I. (1970). Visual perception of rapidly presented word sequences.",
        config: { chunkSize: 1, orpCentering: false, guideLines: false, bionicBolding: false, wpm: 300, orpOffset: 0.5, skipInterval: 50 }
    },
    orp_focused: {
        id: "orp_focused",
        label: "ORP Alignment",
        citation: "Rayner, K. (1998). Eye movements in reading and information processing.",
        config: { chunkSize: 1, orpCentering: true, guideLines: true, bionicBolding: false, wpm: 350, orpOffset: 0.35, skipInterval: 50 }
    },
    cognitive: {
        id: "cognitive",
        label: "Cognitive Chunking",
        citation: "Miller, G. A. (1956). The magical number seven, plus or minus two.",
        config: { chunkSize: 3, orpCentering: false, guideLines: true, bionicBolding: true, wpm: 250, orpOffset: 0.5, skipInterval: 50 }
    },
    typographic: {
        id: "typographic",
        label: "Typographic Guidance",
        citation: "Schotter, E. R., et al. (2012). Parafoveal processing in reading.",
        config: { chunkSize: 1, orpCentering: true, guideLines: false, bionicBolding: true, wpm: 300, orpOffset: 0.4, skipInterval: 50 }
    }
};
