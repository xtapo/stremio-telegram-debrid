const fs = require('fs');

async function findStart() {
    const jsRes = await fetch("https://embed18.streamc.xyz/player.js?ver=1.8", { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const jsCode = await jsRes.text();

    const matches = [...jsCode.matchAll(/addEventListener/g)];
    for (const m of matches) {
        console.log("Match addEventListener at:", m.index);
        console.log(jsCode.substring(m.index - 50, m.index + 200));
        console.log("-------------------");
    }
}

findStart().catch(console.error);
