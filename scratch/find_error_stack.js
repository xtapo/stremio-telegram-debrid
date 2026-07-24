const vm = require('vm');

async function findError() {
    const embedUrl = "https://embed14.streamc.xyz/embed.php?hash=1b8f31744ef1d065cd3aaa250c4eb682";
    const res1 = await fetch(embedUrl, { headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://phim.nguonc.com/' } });
    const html = await res1.text();
    const obfMatch = html.match(/data-obf="([^"]+)"/);
    const obfData = JSON.parse(Buffer.from(obfMatch[1], 'base64').toString('utf-8'));

    const jsRes = await fetch("https://embed14.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    const mockJw = {
        setup: (cfg) => mockJw,
        on: () => mockJw
    };

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
            addEventListener: () => {},
            getElementById: () => ({ dataset: { obf: obfMatch[1] }, appendChild: () => {}, style: {} }),
            querySelector: () => null,
            querySelectorAll: () => []
        },
        window: {
            location: { href: embedUrl, origin: 'https://embed14.streamc.xyz' },
            streamURL: '/' + obfData.sUb + '?d=1',
            videoHash: obfData.hD,
            jwplayer: () => mockJw
        },
        navigator: { userAgent: 'Mozilla/5.0', platform: 'Win32' },
        devtoolsDetector: { launch: () => {}, addListener: () => {} },
        setTimeout: setTimeout,
        clearTimeout: clearTimeout,
        setInterval: () => {},
        clearInterval: () => {}
    };

    const context = vm.createContext(sandbox);

    try {
        vm.runInContext(jsCode, context);
        console.log("vm.runInContext finished without error!");
    } catch (e) {
        console.error("VM RUN ERROR:", e.stack || e);
    }
}

findError().catch(console.error);
