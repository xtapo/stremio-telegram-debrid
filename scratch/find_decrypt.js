const fs = require('fs');

async function findDecryptM3U8Usage() {
    const jsRes = await fetch("https://embed14.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    const idx = jsCode.indexOf('decryptM3U8');
    if (idx !== -1) {
        console.log("Found decryptM3U8 at index", idx);
        console.log("Surrounding code:\n", jsCode.substring(idx - 100, idx + 800));
    }
}

findDecryptM3U8Usage().catch(console.error);
