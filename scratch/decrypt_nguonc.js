const embedUrl = 'https://embed14.streamc.xyz/embed.php?hash=1b8f31744ef1d065cd3aaa250c4eb682';

async function testDecrypt() {
    const res1 = await fetch(embedUrl, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': 'https://phim.nguonc.com/'
        }
    });
    const html = await res1.text();
    const obfMatch = html.match(/data-obf="([^"]+)"/);
    if (!obfMatch) {
        console.error("data-obf not found");
        return;
    }
    const obfData = JSON.parse(Buffer.from(obfMatch[1], 'base64').toString('utf-8'));

    const jsRes = await fetch('https://embed14.streamc.xyz/player.js?ver=1.8', {
        headers: { 'User-Agent': 'Mozilla/5.0' }
    });
    const jsCode = await jsRes.text();

    const fakePlayer = {
        dataset: { obf: obfMatch[1] },
        appendChild: () => {},
        style: {}
    };

    let capturedM3u8Text = null;

    const mockJwPlayerInstance = {
        setup: function(cfg) {
            console.log("\n🎉 JWPLAYER SETUP CALLED!");
            console.log("Config:", cfg);
            return mockJwPlayerInstance;
        },
        on: function(evt, fn) { return mockJwPlayerInstance; }
    };

    const mockJwPlayer = function(id) {
        return mockJwPlayerInstance;
    };

    const baseWindow = {
        location: { reload: () => {}, href: embedUrl, origin: 'https://embed14.streamc.xyz' },
        oncontextmenu: null,
        jwplayer: mockJwPlayer,
        URL: {
            createObjectURL: (blob) => {
                console.log("\n🎉 URL.createObjectURL CALLED with blob!");
                if (blob) {
                    console.log("Blob type:", blob.type);
                    if (blob.text) {
                        blob.text().then(t => {
                            console.log("Decrypted M3U8 Content:\n", t.substring(0, 500));
                        });
                    }
                }
                return "blob:https://embed14.streamc.xyz/fake-decrypted-m3u8";
            },
            revokeObjectURL: () => {}
        }
    };

    const windowProxy = new Proxy(baseWindow, {
        get: (target, prop) => {
            if (prop in target) return target[prop];
            if (typeof prop === 'string' && prop.endsWith('er')) {
                return mockJwPlayer;
            }
            return undefined;
        }
    });

    const fakeDoc = {
        addEventListener: (evt, fn) => {
            if (evt === 'DOMContentLoaded') {
                setTimeout(fn, 10);
            }
        },
        getElementById: (id) => fakePlayer,
        querySelector: () => fakePlayer,
        querySelectorAll: () => [fakePlayer],
        createElement: () => ({ appendChild: () => {}, setAttribute: () => {} })
    };

    global.window = windowProxy;
    global.document = fakeDoc;
    global.navigator = { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', platform: 'Win32', maxTouchPoints: 0 };
    global.devtoolsDetector = { launch: () => {}, addListener: () => {} };

    const vm = require('vm');
    const context = vm.createContext({
        console: console,
        fetch: fetch,
        crypto: globalThis.crypto,
        TextEncoder: TextEncoder,
        TextDecoder: TextDecoder,
        atob: atob,
        btoa: btoa,
        Buffer: Buffer,
        document: fakeDoc,
        window: windowProxy,
        navigator: global.navigator,
        devtoolsDetector: global.devtoolsDetector,
        jwplayer: mockJwPlayer,
        URL: global.window.URL,
        Blob: globalThis.Blob,
        setTimeout: setTimeout,
        clearTimeout: clearTimeout,
        setInterval: setInterval,
        clearInterval: clearInterval
    });

    vm.runInContext(jsCode, context);
}

testDecrypt().catch(console.error);
