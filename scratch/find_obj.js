const fs = require('fs');

async function findObj() {
    const jsRes = await fetch("https://embed14.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    const matches = [...jsCode.matchAll(/_0x2f5bb2/g)];
    for (const m of matches) {
        console.log("Match at index", m.index);
        console.log("Context:\n", jsCode.substring(m.index - 50, m.index + 200));
        console.log("--------------------------------");
    }
}

findObj().catch(console.error);
