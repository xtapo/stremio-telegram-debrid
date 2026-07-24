const vm = require('vm');

async function testHoist() {
    const jsRes = await fetch("https://embed14.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    console.log("jsCode length:", jsCode.length);

    const sandbox = {
        console: console,
        fetch: fetch,
        crypto: globalThis.crypto,
        TextEncoder: TextEncoder,
        TextDecoder: TextDecoder,
        atob: atob,
        btoa: btoa,
        Buffer: Buffer
    };

    const context = vm.createContext(sandbox);

    // Test running script with timeout 2000ms
    try {
        const script = new vm.Script(jsCode);
        script.runInContext(context, { timeout: 2000 });
        console.log("Script executed cleanly!");
    } catch (e) {
        console.error("VM error:", e);
    }
}

testHoist().catch(console.error);
