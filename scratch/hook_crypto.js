const fs = require('fs');
const vm = require('vm');

async function evalKeys() {
    const jsRes = await fetch("https://embed14.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    // Hook crypto.subtle calls to print key material!
    const origCrypto = globalThis.crypto;
    const customSubtle = {
        importKey: async (...args) => {
            console.log("👉 importKey called with args:", args[0], args[1] instanceof Uint8Array ? Buffer.from(args[1]).toString('utf-8') : args[1], args[2]);
            return origCrypto.subtle.importKey(...args);
        },
        digest: async (...args) => {
            console.log("👉 digest called with algo:", args[0], "data len:", args[1].byteLength);
            return origCrypto.subtle.digest(...args);
        },
        decrypt: async (...args) => {
            console.log("👉 decrypt called with algo:", args[0], "data len:", args[2].byteLength);
            return origCrypto.subtle.decrypt(...args);
        }
    };

    const mockJw = {
        setup: function(cfg) {
            return mockJw;
        },
        on: function(evt, fn) { return mockJw; }
    };

    const sandboxWindow = {
        location: { href: "https://embed14.streamc.xyz/embed.php?hash=30fa9e72a99c1cb3dabdf8a2e4222061", origin: 'https://embed14.streamc.xyz' },
        streamURL: '/eyJoOiIzMGZhOWU3MmE5OWMxY2IzZGFiZGY4YTJlNDIyMjA2MSIsInQiOiI1YTNhZTA5YTdlZjBiMTZmMzRjMWE3YzJlNzAxNjI1ZGMyZDQwMjgzNjA5YjQwZGQwOTJmMWQ4MTFkMDI4YTNkIn0=?d=1',
        videoHash: '30fa9e72a99c1cb3dabdf8a2e4222061',
        jwplayer: function(id) { return mockJw; }
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

    const sandbox = {
        console: console,
        fetch: fetch,
        crypto: { subtle: customSubtle },
        TextEncoder: TextEncoder,
        TextDecoder: TextDecoder,
        atob: atob,
        btoa: btoa,
        Buffer: Buffer,
        document: {
            addEventListener: () => {},
            getElementById: () => ({ dataset: { obf: "eyJzVWIiOiJleUpvSWpvaU16Qm1ZVGxsTnpKaE9UbGpNV05pTTJSaFltUm1PR0V5WlRReU1qSXdOakVpTENKMElqb2lOV0V6WVdVd09XRTNaV1l3WWpFMlpqTTBZekZoTjJNeVpUY3dNVFl5TldSak1tUTBNREk0TXpZd09XSTBNR1JrTURreVpqRmtPREV4WkRBeU9HRXpaQ0o5IiwiaEQiOiIzMGZhOWU3MmE5OWMxY2IzZGFiZGY4YTJlNDIyMjA2MSJ9" }, appendChild: () => {}, style: {} }),
            querySelector: () => null,
            querySelectorAll: () => []
        },
        window: windowProxy,
        navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', platform: 'Win32' },
        devtoolsDetector: { launch: () => {}, addListener: () => {} },
        setTimeout: (fn) => setTimeout(fn, 1),
        setInterval: () => 1
    };


    const context = vm.createContext(sandbox);
    vm.runInContext(jsCode, context);
}

evalKeys().catch(console.error);
