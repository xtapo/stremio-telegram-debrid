const fs = require('fs');

async function deobfuscateKey() {
    const jsRes = await fetch("https://embed14.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    // Create a VM context that evaluates function expressions in player.js
    const vm = require('vm');
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
    
    // Evaluate initial array and decoder function definitions (first ~2000 chars)
    const initCode = jsCode.substring(0, 5000);
    vm.runInContext(initCode, context);

    // Now search for strings returned by helper functions
    console.log("Sandbox keys:", Object.keys(sandbox));
}

deobfuscateKey().catch(console.error);
