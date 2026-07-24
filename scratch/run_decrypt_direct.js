const vm = require('vm');

async function testDirectDecrypt() {
    const embedUrl = "https://embed14.streamc.xyz/embed.php?hash=1b8f31744ef1d065cd3aaa250c4eb682";
    const res1 = await fetch(embedUrl, { headers: { 'User-Agent': 'Mozilla/5.0', 'Referer': 'https://phim.nguonc.com/' } });
    const html = await res1.text();
    const obfMatch = html.match(/data-obf="([^"]+)"/);
    const obfData = JSON.parse(Buffer.from(obfMatch[1], 'base64').toString('utf-8'));
    const sUb = obfData.sUb;

    const jsRes = await fetch("https://embed14.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    let decryptedM3U8Text = null;
    let domListeners = [];

    const mockJw = {
        setup: function(cfg) {
            console.log("🎉 JWPLAYER SETUP CALLED!");
            console.log("Config keys:", Object.keys(cfg));
            if (cfg.playlist) console.log("Playlist:", cfg.playlist);
            if (cfg.file) console.log("File URL:", cfg.file);
            return mockJw;
        },
        on: function(evt, fn) { return mockJw; }
    };

    const sandboxWindow = {
        location: { href: embedUrl, origin: 'https://embed14.streamc.xyz' },
        streamURL: '/' + sUb + '?d=1',
        videoHash: obfData.hD,
        jwplayer: function(id) { return mockJw; },
        addEventListener: (evt, fn) => {
            console.log("Window addEventListener:", evt);
            domListeners.push(fn);
        },
        URL: {
            createObjectURL: (blob) => {
                console.log("🎉 URL.createObjectURL called! Blob size:", blob ? blob.size : 0);
                if (blob && blob.text) {
                    blob.text().then(t => {
                        decryptedM3U8Text = t;
                        console.log("\n================ DECRYPTED M3U8 ================");
                        console.log(t.substring(0, 500));
                        console.log("================================================\n");
                    });
                }
                return "blob:https://embed14.streamc.xyz/fake-m3u8";
            },
            revokeObjectURL: () => {}
        }
    };

    const windowProxy = new Proxy(sandboxWindow, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            if (typeof prop === 'string' && prop.endsWith('er')) {
                return function() { return mockJw; };
            }
            return undefined;
        }
    });

    const sandboxDoc = {
        addEventListener: (evt, fn) => {
            console.log("Doc addEventListener:", evt);
            domListeners.push(fn);
        },
        getElementById: () => ({ dataset: { obf: obfMatch[1] }, appendChild: () => {}, style: {} }),
        querySelector: () => null,
        querySelectorAll: () => []
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
        document: sandboxDoc,
        window: windowProxy,
        navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', platform: 'Win32' },
        devtoolsDetector: { launch: () => {}, addListener: () => {} },
        setTimeout: setTimeout,
        clearTimeout: clearTimeout,
        setInterval: () => {},
        clearInterval: () => {}
    };

    const context = vm.createContext(sandbox);
    vm.runInContext(jsCode, context);

    console.log("Total listeners registered:", domListeners.length);
    for (const fn of domListeners) {
        try {
            const ret = fn();
            if (ret && ret.then) {
                console.log("Listener returned Promise, awaiting...");
                await ret;
                console.log("Listener promise finished!");
            }
        } catch(e) {
            console.error("Listener error:", e);
        }
    }

    for (let i = 0; i < 40; i++) {
        if (decryptedM3U8Text) break;
        await new Promise(r => setTimeout(r, 100));
    }
}

testDirectDecrypt().catch(console.error);
