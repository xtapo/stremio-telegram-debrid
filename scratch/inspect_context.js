const vm = require('vm');

async function inspectContext() {
    const embedUrl = "https://embed14.streamc.xyz/embed.php?hash=1b8f31744ef1d065cd3aaa250c4eb682";
    const res1 = await fetch(embedUrl, { headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://phim.nguonc.com/' } });
    const html = await res1.text();
    const obfMatch = html.match(/data-obf="([^"]+)"/);
    const obfData = JSON.parse(Buffer.from(obfMatch[1], 'base64').toString('utf-8'));
    const sUb = obfData.sUb;

    const jsRes = await fetch("https://embed14.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    const sandbox = {
        console: console,
        fetch: fetch,
        crypto: globalThis.crypto,
        TextEncoder: TextEncoder,
        TextDecoder: TextDecoder,
        atob: atob,
        btoa: btoa,
        Buffer: Buffer,
        document: {
            addEventListener: (evt, fn) => {
                console.log("[DOC ADD EVENT]", evt, fn);
            },
            getElementById: () => ({ dataset: { obf: obfMatch[1] }, appendChild: () => {}, style: {} }),
            querySelector: () => null,
            querySelectorAll: () => []
        },
        window: {
            location: { href: embedUrl, origin: 'https://embed14.streamc.xyz' },
            streamURL: '/' + sUb + '?d=1',
            videoHash: obfData.hD,
            addEventListener: (evt, fn) => {
                console.log("[WIN ADD EVENT]", evt, fn);
            }
        },
        navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', platform: 'Win32' },
        devtoolsDetector: { launch: () => {}, addListener: () => {} },
        setTimeout: (fn, delay) => {
            console.log("[SET TIMEOUT]", delay);
            return 1;
        },
        setInterval: () => 1
    };

    const context = vm.createContext(sandbox);
    vm.runInContext(jsCode, context);
}

inspectContext().catch(console.error);
